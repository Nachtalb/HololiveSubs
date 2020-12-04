#!/usr/bin/env python
# -*- coding: utf-8 -*-

import twitter
from pathlib import Path
import time


api = twitter.Api(consumer_key='',
                  consumer_secret='',
                  access_token_key='',
                  access_token_secret='')

channels = {
    'tokino_sora': 'Tokino Sora',
    'AZKi_VDiVA': 'AZKi',
    'robocosan': 'Roboco San',
    'sakuramiko35': 'Sakura Miko',
    'shirakamifubuki': 'Shirakami Fubuki',
    'natsuiromatsuri': 'Natsuiro Matsuri',
    'yozoramel': 'Yozora Mel',
    'akaihaato': 'Akai Haato',
    'akirosenthal': 'Aki Rosenthal',
    'minatoaqua': 'Minato Aqua',
    'yuzukichococh': 'Yuzuki Choco',
    'nakiriayame': 'Nakiri Ayame',
    'murasakishionch': 'Murasaki Shion',
    'oozorasubaru': 'Oozora Subaru',
    'ookamimio': 'Ookami Mio',
    'nekomataokayu': 'Nekomata Okayu',
    'inugamikorone': 'Inugami Korone',
    'shiranuiflare': 'Shiranui Flare',
    'shiroganenoel': 'Shirogane Noel',
    'houshoumarine': 'Houshou Marine',
    'usadapekora': 'Usada Pekora',
    'uruharushia': 'Uruha Rushia',
    'suisei_hosimati': 'Hoshimachi Suisei',
    'amanekanatach': 'Amane Kanata',
    'kiryucoco': 'Kiryu Coco',
    'tsunomakiwatame': 'Tsunomaki Watame',
    'tokoyamitowa': 'Tokoyami Towa',
    'himemoriluna': 'Himemori Luna',
}

holomembers_list = ''
data_file = Path(__file__).absolute().parent / 'www/stats'

data_file.write_text('')
with data_file.open('a') as file:
    for user in reversed(sorted(api.GetListMembersPaged(holomembers_list)[2], key=lambda e: e.followers_count)):
        file.write(f'{channels[user.screen_name]},@{user.screen_name},{user.followers_count},{user.profile_image_url_https.replace("_normal", "")}\n')
print(time.asctime())
