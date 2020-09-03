import tqdm
from selenium.webdriver.common.action_chains import ActionChains
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
from optparse import OptionParser
import time
from beautifultable import BeautifulTable
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
import warnings
warnings.simplefilter("ignore")

SUPER_SAVER_SET_TOKENS = {'Sparbillett', 'Supersaver ticket available'}
MAX_ITER = 10


def is_first_class_ticket(driver, wait, button_idx):
    action = webdriver.common.action_chains.ActionChains(driver)
    reiterate = True

    counter = 0
    while reiterate:
        try:
            blockers = driver.find_elements_by_xpath("//div[@id='j_idt2587']") # SBB might change it
            reiterate = not (len(blockers) > 0)
        except:
            time.sleep(0.1)
            counter += 1
            if counter >= MAX_ITER:
                reiterate = False

    while blockers[0].value_of_css_property('display') != 'none':
        time.sleep(0.1)

    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='mod_timetable_cta leistungOfferierenWrapper updatableForAbPreis']")))
    except:
        pass
    reiterate = True
    while reiterate:
        try:
            button = driver.find_elements_by_xpath("//div[@class='mod_timetable_cta leistungOfferierenWrapper updatableForAbPreis']")[button_idx]
            action.move_to_element_with_offset(button, 5, 5)
            reiterate = False
        except:
            time.sleep(0.1)
    action.click()
    action.perform()
    try:
        button.click()
    except:
        pass

    wait.until(EC.presence_of_element_located((By.XPATH, "//p[@class='mod_totalprice_wrapper_value']")))

    # They ALWAYS display the price for 2nd class. But sometimes the 1st is cheaper!
    final_price = float(driver.find_element_by_xpath("//p[@class='mod_totalprice_wrapper_value']").text.split()[-1])
    labels = driver.find_elements_by_xpath("//span[@class='mod_ws_toggle_button_additional_label']")
    assert len(labels) == 2
    text_class1 = labels[1].text.strip()

    first_class = text_class1 == ''
    supp = text_class1.split()[-1].strip() if not first_class else ''

    if supp == '0.00':
        first_class = True
        supp = ''

    driver.back()
    return first_class, final_price, supp


def find_fill(name, val, driver):
    elem = driver.find_element_by_name(name)
    elem.clear()
    time.sleep(0.1)
    elem.send_keys(val)


def extend(xpath, NB_PREV_AFTER, driver, wait):
    counter = 0

    while counter < NB_PREV_AFTER:
        try:
            driver.find_element_by_xpath(xpath).click()
            counter += 1
        except:
            time.sleep(0.1)
    time.sleep(0.5)


def find_offer(FROM, TO, DATE, TIME, NB_PREV_AFTER):
    def extract_info(text_offer, button_idx, is_supersaver, driver, wait):
        tokens = text_offer.split()
        chf_index = tokens.index('CHF')
        price = float(tokens[chf_index + 1])
        first_class = False
        supp = ''
        if is_supersaver:
            first_class, price, supp = is_first_class_ticket(driver, wait, button_idx)

        departure, arrival, duration = None, None, None

        for line in text_offer.split('\n'):
            line = line.lower().strip()
            if line.startswith('departure'):
                departure = line.split()[-1]
            elif line.startswith('arrival'):
                arrival = line.split()[-1]
            elif line.endswith('min'):
                duration = line

        assert departure is not None and arrival is not None and duration is not None

        dh, dm = departure.split(':')
        ah, am = arrival.split(':')

        return {'price':price,
                'dep_date':DATE.replace(hour=int(dh), minute=int(dm)),
                'arr_date':DATE.replace(hour=int(ah), minute=int(am)),
                'dur':duration,
                'first':first_class,
                'supp for 1st':supp}

    def compute_duration_in_minute(str_time):
        tmp = str_time.split()
        h, m = tmp[0], tmp[2]
        return int(h)*60 + int(m)
    print('Initializing the driver')
    driver = start_driver(WINDOW_SIZE)
    wait = WebDriverWait(driver, 20)

    driver.get("https://www.sbb.ch/en/buying/pages/fahrplan/fahrplan.xhtml")

    print('Entering information')
    find_fill('shopForm_von_valueComp', FROM, driver)
    find_fill('shopForm_nach_valueComp', TO, driver)
    find_fill('shopForm_datepicker_valueComp', datetime.strftime(DATE, '%a, %d.%m.%Y'), driver)
    find_fill('shopForm_timepicker_valueComp', TIME, driver)
    driver.find_element_by_xpath("//button[@class='text__primarybutton button verbindungSuchen']").click()

    print('Gathering routes')
    extend("//span[@id='verbindungsUebersicht_fruehereVerbindungenSuchen']", NB_PREV_AFTER, driver, wait)
    extend("//span[@id='verbindungsUebersicht_spaetereVerbindungenSuchen']", NB_PREV_AFTER, driver, wait)
    time.sleep(1)

    reiterate = True
    while reiterate:
        try:
            # Find multiple dates if trips might be on another day
            all_dates = [(date.location['y'], datetime.strptime(date.text.strip(), '%a, %d.%m.%Y')) for date in driver.find_elements_by_xpath("//p[@class='mod_timetable_day_change']")]
            assert 1 <= len(all_dates) <= 3
            reiterate = False
        except:
            time.sleep(0.1)

    reiterate = True
    while reiterate:
        try:
            buttons_text = [(button_text.text, button_text) for button_text in driver.find_elements_by_xpath("//div[contains(@class, 'sbb_mod_ext mod_accordion_item var_timetable')]")]
            reiterate = False
        except:
            time.sleep(0.1)

    text_offers = [(button[0], button[1], i, 'CHF' in button[0]) for i, button in enumerate(buttons_text)]
    text_offers = [(x[0], x[1], x[2], x[3], len(set(x[0].split('\n')).intersection(SUPER_SAVER_SET_TOKENS)) > 0) for x in text_offers] # Add whether the offer is a super saver ticket or not!

    offers = []
    for text, button, idx, is_valid, is_supersaver in tqdm.tqdm(text_offers, desc='Finding the best options'):
        if not is_valid:
            continue

        offer_dict = extract_info(text, idx, is_supersaver, driver, wait)
        if compute_duration_in_minute(offer_dict['dur']) <= args.max_duration:
            offers.append(offer_dict)

        if len(all_dates) > 1: # Need to fix dates
            if button.location['y'] > all_dates[0][0] and button.location['y'] < all_dates[1][0]:
                offer_dict['dep_date'] = offer_dict['dep_date'].replace(day=all_dates[0][1].day, month=all_dates[0][1].month, year=all_dates[0][1].year)
            else:
                offer_dict['dep_date'] = offer_dict['dep_date'].replace(day=all_dates[1][1].day, month=all_dates[1][1].month, year=all_dates[1][1].year)

    driver.close()
    driver.quit()

    offers = [(offer['price'], offer['first'], offer['supp for 1st'], offer['dep_date'], offer['dur'], offer['arr_date']) for offer in offers]
    return sorted(offers, key=lambda x: x[0], reverse=False)


def start_driver(WINDOW_SIZE, driver_path='./chromedriver'):
    browser_options = Options()
    browser_options.add_argument("--headless")
    browser_options.add_argument("--window-size=%s" % WINDOW_SIZE)
    return webdriver.Chrome(driver_path, options=browser_options)


def look_up_offers(FROM, TO, DATE, TIME, options):
    output = '\nTop {} offers {} -> {} around {} {}\n'.format(options.topk, FROM, TO, datetime.strftime(DATE, '%a %d %b'), TIME)

    table = BeautifulTable(max_width=100)
    table.column_headers = ['CHF', 'Class', 'Supp 1st', 'DepT', 'ArrT', 'Dur', 'DepD']
    for offer_dict in find_offer(FROM, TO, DATE, TIME, options.nb_prev_after)[:options.topk]:
        tmp = offer_dict[4].split()
        dur_h, dur_m = tmp[0], tmp[2]
        row = ['{:.2f}'.format(offer_dict[0]),
               offer_dict[1],
               offer_dict[2],
               datetime.strftime(offer_dict[3], '%H:%M'),
               datetime.strftime(offer_dict[5], '%H:%M'),
               '{}:{:02d}'.format(dur_h, int(dur_m)),
               datetime.strftime(offer_dict[3], '%a %d %b')]
        table.append_row(row=row)
    return output, table


if __name__ == '__main__':
    parser = OptionParser()
    today = datetime.now()
    two_weeks = today + timedelta(days=14)
    parser.add_option('--nb_prev_after', type=int, default=2)
    parser.add_option('--from_station', type=str, default='Zürich HB')
    parser.add_option('--to_station', type=str, default='Neuchâtel')
    parser.add_option('--day', type=int, default=two_weeks.day)
    parser.add_option('--month', type=int, default=two_weeks.month)
    parser.add_option('--year', type=int, default=two_weeks.year)
    parser.add_option('--time', type=str, default=two_weeks.time().strftime('%H:%M'))
    parser.add_option('--topk', type=int, default=15)
    parser.add_option('--max_duration', type=int, default=180)
    parser.add_option('--reversed', action="store_true", default=False)
    (args, _) = parser.parse_args()
    DATE = datetime(day=args.day, month=args.month, year=args.year)
    WINDOW_SIZE = "1920,1080"

    print('Computing prices for: {} -> {} around {}/{}/{} at {} with a max duration of {} minutes. The operation will take approximately two minutes.'.format(args.from_station, args.to_station, args.day, args.month, args.year, args.time, args.max_duration))
    from_station, to_station = args.from_station, args.to_station
    if args.reversed:
        from_station, to_station = to_station, from_station

    start_time = time.time()
    output, table = look_up_offers(from_station, to_station, DATE, args.time, args)
    print(output)
    print(table)
    stop_time = time.time()
    print('\n\nExecution in {:.2f} seconds'.format(stop_time - start_time))
