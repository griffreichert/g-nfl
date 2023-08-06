import pandas as pd
import datetime as dt

year = dt.datetime.now().year
week = 1
# URL for the website to scrape schedule and betting data
nflgamedata_url = f'https://nflgamedata.com/schedule.php?season={year}&week={week}'

print(nflgamedata_url)