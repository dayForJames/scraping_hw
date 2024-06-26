from bs4 import BeautifulSoup
import calendar
import datetime as DT
from urllib.parse import urljoin, urlparse
import re
import time

teams = set()

class CssSelectorParser:
    def parse(self, content, current_url):
        netloc = urlparse(current_url).netloc
        scheme = urlparse(current_url).scheme
        domain = scheme + "://" + netloc
        self._domain = domain

        soup = BeautifulSoup(content, "html.parser")
        table = soup.select_one("table.infobox")

        result = None
        urls = []

        if table is None:
            raise Exception("404")

        table = table.attrs.get("data-name")

        if "Соревнование футбольных сборных" in table:
            result, urls = self._main_page_parse(soup)
        elif "Сборная страны по футболу" in table:
            result, urls = self._team_parse(soup)
        elif "Футболист" in table:
            result, urls = self._player_parse(soup, current_url)

        return result, urls

    def _main_page_parse(self, data):
        """Find table with all teams that will participate, find all links in row and take the last that goes to country team page"""

        team_table = data.find(id="Квалифицировались_в_финальный_турнир").find_next(
            "table", {"class": "standard sortable"}
        )
        all_web_links = []

        for row in team_table.find_all("tr")[1:]:
            col = row.find("td")
            url = col.select("a")[-1]

            if url is not None:
                teams.add(url.get('title').strip("\n\r"))
                all_web_links.append(self._domain + url.get("href"))

        return None, all_web_links

    def _find_relevant_tags(self, data, headers):
        tags = []

        for header in headers:
            tag = data.find('span', {'id' : header})
            if tag is not None:
                tags.append(tag)

        return tags

    def _team_parse(self, data):
        tables = []
        actual_web_links = []

        headers = [
            "Текущий_состав",
            "Текущий_состав_сборной",
            "Состав",
            "Состав_сборной",
            'Недавние_вызовы',
        ]

        relevant_tags = self._find_relevant_tags(data, headers)

        for tag in relevant_tags:
            table = tag.find_next("table", {"class": "wikitable"})

            if table is not None:
                tables.append(table)

        for table in tables:
            if table is None:
                continue

            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")

                if len(cols) < 2:
                    continue

                url = self._domain + cols[2].find("a").get("href")
                actual_web_links.append(url)

        return None, actual_web_links

    def _get_bday(self, day : str, month : str, year : str) -> list:
        months = [
            "января",
            "февраля",
            "марта",
            "апреля",
            "мая",
            "июня",
            "июля",
            "августа",
            "сентября",
            "октября",
            "ноября",
            "декабря",
        ]

        month_num = months.index(month) + 1
        utc_timestamp = int(calendar.timegm(DT.datetime(int(year), month_num, int(day), 0, 0, 0).utctimetuple()))

        return utc_timestamp, f"{year}.{month_num}.{day}"

    def _calc_height(self, text_height : str) -> int:
        return int(re.match(r"\b\d+\b", text_height).group(0))

    def _calc_club_goals(self, player_data, goals):
        re_goals = re.search(r"\b\d+\b", goals)

        if re_goals is not None:
            re_goals = int(re_goals.group(0))
        else:
            re_goals = 0

        if player_data["position"] == "вратарь":
            player_data["club_conceded"] += int(re_goals)
        else:
            player_data["club_scored"] += int(re_goals)

    def _process_national_additional_table(self, data, player_data):
        relevant_tag = [data.find(id=tag) for tag in ["Статистика_в_сборной", 'Матчи_за_сборную'] if data.find(id=tag) is not None]

        if (not len(relevant_tag)):
            return

        table = relevant_tag[0].find_next('table')

        last_row = table.find_all("tr")[-1]
        cols = last_row.find_all("th")

        if len(cols) != 0 and cols[0].text.strip() == "Итого":
            goals = int(re.search(r"\b\d+\b", cols[2].text.strip()).group(0))
            matches = int(cols[1].text.strip())

            if player_data["national_caps"] < matches:
                player_data["national_caps"] = matches

            if player_data["position"] == "вратарь":
                if player_data["national_conceded"] < goals:
                    player_data["national_conceded"] = goals
            else:
                if player_data["national_scored"] < goals:
                    player_data["national_scored"] = goals

    def _process_club_additional_table(self, data, player_data):
        relevant_tag = [
            data.find(id=tag)
            for tag in [
                "Клубная_статистика",
                "Статистика_выступлений",
                "Клубная",
                "Статистика",
            ]
            if data.find(id=tag) is not None
        ]

        if (not len(relevant_tag)):
            return

        table = relevant_tag[0].find_next("table")

        last_row = table.find_all("tr")[-1]
        cols_th = last_row.find_all("th")
        cols_td = last_row.find_all("td")
        cols = []

        if len(cols_td) > len(cols_th):
            cols = cols_td
        else:
            cols = cols_th

        if (
            len(cols_th) != 0
            and cols_th[0].text.strip() in ["Всего за карьеру", "Всего"]
        ) or (
            len(cols_td) != 0
            and cols_td[0].text.strip() in ["Всего за карьеру", "Всего"]
        ):
            matches = cols[-2].text.strip()
            goals = 0
            is_diff_location = False

            #   Matches may be swaped with goals on some pages
            if not matches[0].isnumeric():
                goals = int(matches[1:])
                matches = int(cols[-3].text.strip())
                is_diff_location = True
            else:
                matches = int(cols[-2].text.strip())

            if player_data["club_caps"] < matches:
                player_data["club_caps"] = matches

            if player_data["position"] == "вратарь":
                if not is_diff_location:
                    goals = re.search(r'\b\d+\b', cols[-1].text.strip())

                    if goals is not None:
                        goals = int(goals.group(0))
                    else:
                        goals = 0

                if player_data["club_conceded"] < goals:
                    player_data["club_conceded"] = goals
            else:
                goals = int(cols[-1].text.strip())

                if player_data["club_scored"] < goals:
                    player_data["club_scored"] = goals

    def _find_player_info_main_table(self, data, player_data):
        national_team_career_ind = 0
        club_career_ind = 0

        has_name = False

        infobox = data.find("table", {"class": "infobox"})
        rows = infobox.find_all("tr")

        for row in rows:
            line_type = row.find("th")

            if line_type is None:
                continue

            line_type_text = line_type.text.strip()

            if not has_name:
                name_line = row.find("div", {"class": "ts_Спортсмен_имя"})

                if  name_line is not None:
                    name = name_line.text.strip().split()

                    if len(name) > 2:
                        name = [" ".join([name[0], name[1]]), name[2]]

                    player_data["name"] = name[::-1]
                    has_name = True

            elif re.search(r"\bРодился\b", line_type_text):
                bday = row.find("span", {"class": "nowrap"}).find_all("a")
                bday[0] = bday[0].text
                bday[1] = bday[1].text

                day, month = bday[0].split()
                year = bday[1]

                utc_timestamp, birth_str = self._get_bday(day, month, year)

                player_data["birth"] = utc_timestamp
                player_data["birt_str"] = birth_str
            elif re.search(r"\bРост\b", line_type_text):
                height = self._calc_height(row.text.strip().split("\n")[2])
                player_data["height"] = height
            elif re.search(r"\bПозиция\b", line_type_text):
                pos = row.find("td").text.strip()
                player_data["position"] = pos
            elif re.search(r"\bКлуб\b", line_type_text):
                club = row.find("span", {"class": "no-wikidata"}).text.strip()
                player_data["current_club"] = club
            elif re.search(r"\bКлубная карьера\b", line_type_text):
                club_career_ind = rows.index(row)
            elif re.search(r"\bНациональная сборная\b", line_type_text):
                national_team_career_ind = rows.index(row)

        if national_team_career_ind == 0:
            national_team_career_ind = len(rows)

        for i in range(club_career_ind + 1, national_team_career_ind, 1):
            td = rows[i].find_all("td")

            if len(td) != 3:
                break

            right_td = td[-1]
            text = right_td.text.strip()

            matches, goals = text.split("(")
            matches = matches.strip()
            goals = goals.strip()[:-1]

            matches = re.search(r"\b\d+\b", matches)

            if matches is not None:
                player_data["club_caps"] += int(matches.group(0))

            self._calc_club_goals(player_data, goals)

        if national_team_career_ind != 0:
            has_national_team = False

            trs = infobox.find_all('tr', {'class': "nowrap odd"})
            last_tr = trs[-1]
            tds = last_tr.find_all('td')
            right_td = tds[-1]
            text = right_td.text.strip()
            team_line = tds[1].find_all("a")[-1]["title"].strip()

            if team_line in teams:
                has_national_team = True
            else:
                trs = infobox.find_all("tr", {"class": "nowrap even"})
                last_tr = trs[-1]
                tds = last_tr.find_all("td")
                right_td = tds[-1]
                text = right_td.text.strip()
                team_line = tds[1].find_all("a")[-1]["title"].strip()

                if team_line in teams:
                    has_national_team = True

            if (has_national_team):
                matches, goals = text.split("(")
                matches = re.search(r"\b\d+\b", matches)
                goals = goals.strip()[:-1]

                if matches is not None:
                    matches = int(matches.group(0))

                player_data["national_caps"] = matches
                player_data["national_team"] = team_line

                goals = re.search(r"\b\d+\b", goals)

                if goals is not None:
                    goals = int(goals.group(0))
                else:
                    goals = 0

                if player_data["position"] == "вратарь":
                    player_data["national_conceded"] = goals
                else:
                    player_data["national_scored"] = goals
            else:
                raise Exception("Player has not played for national team yet")

    def _player_parse(self, data, current_url):
        player_data = {}

        player_data = {
            "url": current_url,
            "name": "",
            "height": 0,
            "position": "",
            "current_club": "",
            "club_caps": 0,
            "club_conceded": 0,
            "club_scored": 0,
            "national_caps": 0,
            "national_conceded": 0,
            "national_scored": 0,
            "national_team": "",
        }

        #   Parse info from main table
        self._find_player_info_main_table(data, player_data)

        #   Check info in detail table
        self._process_club_additional_table(data, player_data)
        #   National team stats
        self._process_national_additional_table(data, player_data)

        return player_data, []
