import time
from selenium import webdriver
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
from optparse import OptionParser
import time
from beautifultable import BeautifulTable
import warnings
warnings.simplefilter("ignore")


def find_fill(name, val, driver):
    elem = driver.find_element_by_name(name)
    elem.clear()
    time.sleep(0.1)
    elem.send_keys(val)


def extend(xpath, NB_PREV_AFTER, driver):
    counter = 0
    while counter < NB_PREV_AFTER:
        try:
            driver.find_element_by_xpath(xpath).click()
            counter += 1
        except:
            time.sleep(0.1)


def find_offer(FROM, TO, DATE, TIME, NB_PREV_AFTER, WAIT_TIME):
    def extract_info(text_offer):
        tokens = text_offer.split()
        chf_index = tokens.index('CHF')
        price = float(tokens[chf_index + 1])

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
                'dur':duration}

    def compute_duration_in_minute(str_time):
        tmp = str_time.split()
        h, m = tmp[0], tmp[2]
        return int(h)*60 + int(m)

    driver = start_driver(WINDOW_SIZE)
    driver.get("https://www.sbb.ch/en/buying/pages/fahrplan/fahrplan.xhtml")

    find_fill('shopForm_von_valueComp', FROM, driver)
    find_fill('shopForm_nach_valueComp', TO, driver)
    find_fill('shopForm_datepicker_valueComp', datetime.strftime(DATE, '%a, %d.%m.%Y'), driver)
    find_fill('shopForm_timepicker_valueComp', TIME, driver)

    driver.find_element_by_xpath("//button[@class='text__primarybutton button verbindungSuchen']").click()
    time.sleep(WAIT_TIME)

    extend("//span[@id='verbindungsUebersicht_fruehereVerbindungenSuchen']", NB_PREV_AFTER, driver)
    extend("//span[@id='verbindungsUebersicht_spaetereVerbindungenSuchen']", NB_PREV_AFTER, driver)
    time.sleep(WAIT_TIME)

    # Find multiple dates if trips might be on another day
    all_dates = [(date.location['y'], datetime.strptime(date.text.strip(), '%a, %d.%m.%Y')) for date in driver.find_elements_by_xpath("//p[@class='mod_timetable_day_change']")]
    assert 1 <= len(all_dates) <= 2
    buttons = driver.find_elements_by_xpath("//div[@class='mod_accordion_item_heading var_timetable']")
    text_offers = [(button.text, button) for button in buttons if 'CHF' in button.text]

    offers = []
    for text, button in text_offers:
        offer_dict = extract_info(text)
        if compute_duration_in_minute(offer_dict['dur']) <= options.max_duration:
            offers.append(offer_dict)

        if len(all_dates) > 1: # Need to fix dates
            if button.location['y'] > all_dates[0][0] and button.location['y'] < all_dates[1][0]:
                offer_dict['dep_date'] = offer_dict['dep_date'].replace(day=all_dates[0][1].day, month=all_dates[0][1].month, year=all_dates[0][1].year)
            else:
                offer_dict['dep_date'] = offer_dict['dep_date'].replace(day=all_dates[1][1].day, month=all_dates[1][1].month, year=all_dates[1][1].year)

    driver.close()
    driver.quit()

    offers = [(offer['price'], offer['dep_date'], offer['dur'], offer['arr_date']) for offer in offers]
    return sorted(offers, key=lambda x: x[0], reverse=False)


def start_driver(WINDOW_SIZE, driver_path='./chromedriver'):
    browser_options = Options()
    browser_options.add_argument("--headless")
    browser_options.add_argument("--window-size=%s" % WINDOW_SIZE)
    return webdriver.Chrome(driver_path, options=browser_options)


def look_up_offers(FROM, TO, DATE, TIME, options):
    output = '\nTop {} offers {} -> {} around {} {}\n'.format(options.topk, FROM, TO, datetime.strftime(DATE, '%a %d %b'), TIME)

    table = BeautifulTable(max_width=100)
    table.column_headers = ['CHF', 'DepT', 'ArrT', 'Dur', 'DepD']
    for offer_dict in find_offer(FROM, TO, DATE, TIME, options.nb_prev_after, options.waiting_time)[:options.topk]:
        tmp = offer_dict[2].split()
        dur_h, dur_m =tmp[0], tmp[2]
        row = ['{:.2f}'.format(offer_dict[0]),
               datetime.strftime(offer_dict[1], '%H:%M'),
               datetime.strftime(offer_dict[3], '%H:%M'),
               '{}:{:02d}'.format(dur_h, int(dur_m)),
               datetime.strftime(offer_dict[1], '%a %d %b')]
        table.append_row(row=row)
    return output, table


if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option('--nb_prev_after', type=int, default=5)
    parser.add_option('--waiting_time', type=int, default=3)
    parser.add_option('--from_station', type=str, default='Zürich HB')
    parser.add_option('--to_station', type=str, default='Neuchâtel')
    parser.add_option('--day', type=int, default=datetime.now().day)
    parser.add_option('--month', type=int, default=datetime.now().month)
    parser.add_option('--year', type=int, default=datetime.now().year)
    parser.add_option('--time', type=str, default=datetime.now().time().strftime('%H:%M'))
    parser.add_option('--topk', type=int, default=8)
    parser.add_option('--max_duration', type=int, default=180)
    parser.add_option('--reversed', action="store_true", default=False)
    (options, args) = parser.parse_args()
    DATE = datetime(day=options.day, month=options.month, year=options.year)
    WINDOW_SIZE = "1920,1080"

    from_station, to_station = options.from_station, options.to_station
    if options.reversed:
        from_station, to_station = to_station, from_station

    start_time = time.time()
    output, table = look_up_offers(from_station, to_station, DATE, options.time, options)
    print(output)
    print(table)
    stop_time = time.time()
    print('\n\nExecution in {:.2f} seconds'.format(stop_time - start_time))
