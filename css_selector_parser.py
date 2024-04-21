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

        # team_table = data.find("table", {"class": "standard sortable"})
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

    def find_relevant_tags(self, data, headers):
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

        relevant_tags = self.find_relevant_tags(data, headers)

        for tag in relevant_tags:
            table = tag.find_next("table", {"class": "wikitable"})

            if table is not None:
                tables.append(table)

        for table in tables:
            if table is None:
                continue

            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")

                if len(cols) == 0 or len(cols) == 1:
                    continue

                url = self._domain + cols[2].find("a").get("href")
                actual_web_links.append(url)

        return None, actual_web_links

    def _standart_text_data(self, text):
        while not text[-1].isalpha():
            text = text[: len(text) - 1]

        return text

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
        birth_str = f"{year}.{month_num}.{day}"
        start = DT.datetime(int(year), int(month_num), int(day), 0, 0, 0)

        utc_tuple = start.utctimetuple()
        utc_timestamp = calendar.timegm(utc_tuple)

        return utc_timestamp, birth_str

    def _calc_height(self, text_height : str) -> int:
        res_height = ""
        height_ind = 0

        while text_height[height_ind].isnumeric():
            res_height += text_height[height_ind]
            height_ind += 1

        if res_height[-1] == "]":
            ind = res_height.index("[")
            res_height = res_height[:ind]

        return int(res_height)

    def _calc_national_goals_main_table(
        self, position, goals, national_conceded, national_goals
    ):
        if position == "вратарь":
            if goals.find("?") != -1:
                national_conceded.append(0)
            else:
                if goals.find("/") != -1:
                    goals = goals[: goals.index("/")]

                if not goals[0].isnumeric():
                    national_conceded.append(int(goals[1:]))
                else:
                    national_conceded.append(int(goals))

        else:
            if goals.find("?") != -1:
                national_goals.append(0)
            else:
                if goals.find("/") != -1:
                    goals = goals[: goals.index("/")]
                national_goals.append(int(goals))

    def _calc_goals(self, player_data, goals):
        #   Для пропущенных голов для вратарей
        if player_data["position"] == "вратарь":
            if goals != "0" and goals.find("?") == -1:
                if goals.find("/") != -1:
                    goals = goals[: goals.index("/")]
                player_data["club_conceded"] += int(goals[1:])
        else:
            if goals.find("?") == -1:
                if goals.find("/") != -1:
                    goals = goals[: goals.index("/")]
                player_data["club_scored"] += int(goals)

    def _process_national_additional_table(self, data, player_data):
        if (
            data.find(id="Статистика_в_сборной") is not None
            or data.find(id="Матчи_за_сборную") is not None
        ):
            tables = data.find_all("table", {"class": "wikitable"})

            for table in tables:
                last_row = table.find_all("tr")[-1]
                cols = last_row.find_all("th")

                if len(cols) != 0 and cols[0].text.strip() in ["Итого"]:
                    if player_data["position"] == "вратарь":
                        matches = int(cols[1].text.strip())

                        goals = cols[2].text.strip()
                        if not goals[0].isnumeric():
                            goals = goals[1:]
                        goals = int(goals)

                        if player_data["national_caps"] < matches:
                            player_data["national_caps"] = matches
                        if player_data["national_conceded"] < goals:
                            player_data["national_conceded"] = goals
                    else:
                        matches = int(cols[1].text.strip())
                        goals = int(cols[2].text.strip())

                        if player_data["national_caps"] < matches:
                            player_data["national_caps"] = matches
                        if player_data["national_scored"] < goals:
                            player_data["national_scored"] = goals

    def _calc_national_info_main_table(self, rows, national_team_career_ind, player_data):
        if national_team_career_ind != 0:
            national_teams = []
            national_matches = []
            national_goals = []
            national_conceded = []

            for i in range(national_team_career_ind + 1, len(rows)):
                tds = rows[i].find_all("td")

                if len(tds) != 3:
                    break

                if tds[-1].find("span", {"class": "reference-text"}) is not None:
                    break

                right_td = tds[-1]
                text = right_td.text.strip()

                team_line = tds[1].find_all("a")[-1]["title"].strip()
                team_line_text = tds[1].find_all("a")[-1].text.strip()

                if (
                    len(team_line) > 0
                    and team_line.find("Флаг") == -1
                    and team_line.find("(") == -1
                    and team_line_text.find("(") == -1
                ):
                    national_teams.append(team_line)

                    matches, goals = "", ""
                    ind = 0

                    while text[ind] != "(":
                        matches += text[ind]
                        ind += 1

                    ind += 1

                    while text[ind] != ")":
                        goals += text[ind]
                        ind += 1

                    if matches.find("?") == -1:
                        national_matches.append(int(matches))

                    self._calc_national_goals_main_table(
                        player_data["position"],
                        goals,
                        national_conceded,
                        national_goals,
                    )

            n_matches = 0
            n_team = None
            n_conceded = 0
            n_scored = 0

            for i in range(len(national_teams)):
                if not (
                    national_teams[i].find("(") != -1
                    or national_teams[i].find("Молодёжная") != -1
                    or national_teams[i].find("Олимпийская") != -1
                    or national_teams[i].find("en:") != -1
                ):

                    if national_teams[i] in teams:
                        n_team = national_teams[i]
                        n_matches = national_matches[i]

                        if player_data["position"] == "вратарь":
                            n_conceded = national_conceded[i]
                        else:
                            n_scored = national_goals[i]

            if n_team is not None:
                player_data["national_caps"] = n_matches
                player_data["national_team"] = n_team

                if player_data["position"] == "вратарь":
                    player_data["national_conceded"] = n_conceded
                else:
                    player_data["national_scored"] = n_scored
            else:
                raise Exception("Player has not played for national team yet")

    def _process_club_additional_table(self, data, player_data):
        tables = data.find_all("table")

        for table in tables:
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
                        goals = cols[-1].text.strip()
                        if not goals[0].isnumeric() and goals != "?":
                            goals = goals[1:]
                        elif goals == "?":
                            goals = "0"
                        goals = int(goals)

                    if player_data["club_conceded"] < goals:
                        player_data["club_conceded"] = goals
                else:
                    goals = int(cols[-1].text.strip())

                    if player_data["club_scored"] < goals:
                        player_data["club_scored"] = goals

                break

    def _calc_club_main_table(self, rows, club_career_ind, national_team_career_ind, player_data):
        for i in range(club_career_ind + 1, national_team_career_ind, 1):
            td = rows[i].find_all("td")

            if len(td) != 3:
                break

            right_td = td[-1]
            text = right_td.text.strip()

            matches, goals = "", ""
            ind = 0

            while text[ind] != "(":
                matches += text[ind]
                ind += 1

            ind += 1

            while text[ind] != ")":
                goals += text[ind]
                ind += 1

            if matches.find("?") == -1:
                player_data["club_caps"] += int(matches)

            self._calc_goals(player_data, goals)

    def _find_player_info(self, rows, player_data):
        national_team_career_ind = 0
        club_career_ind = 0
        
        name = rows[0].find("div", {"class": "ts_Спортсмен_имя"}).text.strip().split()

        if len(name) > 2:
            name = [" ".join([name[0], name[1]]), name[2]]

        player_data["name"] = name[::-1]

        for row in rows[1:]:
            line_type = row.find("th")

            if line_type is None:
                continue

            line_type_text = self._standart_text_data(line_type.text.strip())

            if line_type_text == "Родился":
                bday = row.find("span", {"class": "nowrap"}).find_all("a")
                bday[0] = bday[0].text
                bday[1] = bday[1].text

                day, month = bday[0].split()
                year = bday[1]

                utc_timestamp, birth_str = self._get_bday(day, month, year)

                player_data["birth"] = utc_timestamp
                player_data["birt_str"] = birth_str
            elif line_type_text == "Рост":
                height = self._calc_height(row.text.strip().split("\n")[2])
                player_data["height"] = height
            elif line_type_text == "Позиция":
                pos = row.find("td").text.strip()
                player_data["position"] = pos
            elif line_type_text == "Клуб":
                club = row.find("span", {"class": "no-wikidata"}).text.strip(" ")
                player_data["current_club"] = club
            elif line_type_text == "Клубная карьера":
                club_career_ind = rows.index(row)
            elif line_type_text == "Национальная сборная":
                national_team_career_ind = rows.index(row)

        return club_career_ind, national_team_career_ind

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

        infobox = data.find("table", {"class": "infobox"})
        rows = infobox.find_all("tr")

        club_career_ind, national_team_career_ind = self._find_player_info(
            rows, player_data
        )

        if national_team_career_ind == 0:
            national_team_career_ind = len(rows)

        #   Procceed club career
        self._calc_club_main_table(rows, club_career_ind, national_team_career_ind, player_data)
        #   Proceed national career
        self._calc_national_info_main_table(rows, national_team_career_ind, player_data)
        #   Check info in detail table
        self._process_club_additional_table(data, player_data)
        #   National team stats
        self._process_national_additional_table(data, player_data)

        return player_data, []
