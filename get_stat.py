#!/usr/bin/env python
# -*- coding: utf-8 -*-
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
from subprocess import Popen
import sys

from bilibili_api.user import UserInfo
from dotenv import load_dotenv
import requests
from twitter import Api
from yarl import URL

BASE_PATH = Path(__file__).absolute().parent

load_dotenv(BASE_PATH / '.env')

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger('HololiveStats')

groups = {
    'talents': {
        'name': 'Talents',
        'show_title': False,
        'members': [],
        'order': 1,
    },
    'staff': {
        'name': 'Staff',
        'show_title': True,
        'members': [],
        'order': 2,
    },
    'corp': {
        'name': 'Official Hololive Production',
        'show_title': True,
        'members': [],
        'order': 3,
    },
}

channels = [
    # {'name': '',  'bg': '#', 'fg': '#fff', 'twitter':  '', 'youtube': '', 'bilibili': ''},

    # Japan Gen 0
    {'id': 1, 'name': 'Hoshimachi Suisei', 'bg': '#799acb', 'fg': '#fff', 'twitter':  'suisei_hosimati', 'youtube': 'UC5CwaMl1eIgY8h02uZw7u8A', 'bilibili': '9034870',   'retired': False},
    {'id': 2, 'name': 'Roboco San',        'bg': '#af7425', 'fg': '#fff', 'twitter':  'robocosan',       'youtube': 'UCDqI2jOz0weumE8s7paEk6g', 'bilibili': '20813493',  'retired': False},
    {'id': 3, 'name': 'Sakura Miko',       'bg': '#f6a1a8', 'fg': '#fff', 'twitter':  'sakuramiko35',    'youtube': 'UC-hM6YJuNYVAmUWxeIr9FeA', 'bilibili': '366690056', 'retired': False},
    {'id': 4, 'name': 'Tokino Sora',       'bg': '#be6c5e', 'fg': '#fff', 'twitter':  'tokino_sora',     'youtube': 'UCp6993wxpyDPHUpavwDFqgg', 'bilibili': '286179206', 'retired': False},

    # Japan INoNaKa Music
    {'id': 5, 'name': 'AZKi',              'bg': '#6cbabc', 'fg': '#fff', 'twitter':  'azki_vdiva',      'youtube': 'UC0TXe_LYZ4scaW2XMyi5_kw', 'bilibili': '389056211', 'retired': False},

    # Japan Gen 1
    {'id': 10, 'name': 'Akai Haato',        'bg': '#eabb98', 'fg': '#fff', 'twitter':  'akaihaato',       'youtube': 'UC1CfXB_kRs3C-zaeTG3oGyg', 'bilibili': '339567211', 'retired': False},
    {'id': 11, 'name': 'Aki Rosenthal',     'bg': '#5deaf9', 'fg': '#fff', 'twitter':  'akirosenthal',    'youtube': 'UCFTLzh12_nrtzqBPsTCqenA', 'bilibili': '389857131', 'retired': False},
    {'id': 12, 'name': 'Natsuiro Matsuri',  'bg': '#edad62', 'fg': '#fff', 'twitter':  'natsuiromatsuri', 'youtube': 'UCQ0UDLQCjY0rmuxCDE38FGg', 'bilibili': '336731767', 'retired': False},
    {'id': 13, 'name': 'Shirakami Fubuki',  'bg': '#5eb6d0', 'fg': '#fff', 'twitter':  'shirakamifubuki', 'youtube': 'UCdn5BQ06XqgXoAxIhbqw5Rg', 'bilibili': '332704117', 'retired': False},
    {'id': 14, 'name': 'Yozora Mel',        'bg': '#d7a86a', 'fg': '#fff', 'twitter':  'yozoramel',       'youtube': 'UCD8HOxPs4Xvsm8H0ZxXGiBw', 'bilibili': '389856447', 'retired': False},

    # Japan Gen 2
    {'id': 20, 'name': 'Minato Aqua',       'bg': '#793559', 'fg': '#fff', 'twitter':  'minatoaqua',      'youtube': 'UC1opHUrw8rvnsadT-iGp7Cg', 'bilibili': '375504219', 'retired': False},
    {'id': 21, 'name': 'Murasaki Shion',    'bg': '#4f3756', 'fg': '#fff', 'twitter':  'murasakishionch', 'youtube': 'UCXTpFs_3PqI41qX2d9tL2Rw', 'bilibili': '389857640', 'retired': False},
    {'id': 22, 'name': 'Nakiri Ayame',      'bg': '#bf8996', 'fg': '#fff', 'twitter':  'nakiriayame',     'youtube': 'UC7fk0CB07ly8oSl0aqKkqFg', 'bilibili': '389858027', 'retired': False},
    {'id': 23, 'name': 'Oozora Subaru',     'bg': '#6db2ce', 'fg': '#fff', 'twitter':  'oozorasubaru',    'youtube': 'UCvzGlP9oQwU--Y0r9id_jnA', 'bilibili': '389859190', 'retired': False},
    {'id': 24, 'name': 'Yuzuki Choco',      'bg': '#eb9f74', 'fg': '#fff', 'twitter':  'yuzukichococh',   'youtube': 'UC1suqwovbL1kzsoaZgFZLKg', 'bilibili': '389858754', 'retired': False},

    # Japan Gamers
    {'id': 30, 'name': 'Ookami Mio',        'bg': '#c6535c', 'fg': '#fff', 'twitter':  'ookamimio',       'youtube': 'UCp-5t9SrOQwXMU7iIjQfARg', 'bilibili': '389862071', 'retired': False},
    {'id': 31, 'name': 'Nekomata Okayu',    'bg': '#aa8caf', 'fg': '#fff', 'twitter':  'nekomataokayu',   'youtube': 'UCvaTdHTWBGv3MKj3KVqJVCw', 'bilibili': '412135222', 'retired': False},
    {'id': 32, 'name': 'Inugami Korone',    'bg': '#c88382', 'fg': '#fff', 'twitter':  'inugamikorone',   'youtube': 'UChAnqc_AY5_I3Px5dig3X1Q', 'bilibili': '412135619', 'retired': False},

    # Japan Gen 3
    {'id': 40, 'name': 'Houshou Marine',    'bg': '#dc6e7f', 'fg': '#fff', 'twitter':  'houshoumarine',   'youtube': 'UCCzUftO8KOVkV4wQG1vkUvg', 'bilibili': '454955503', 'retired': False},
    {'id': 41, 'name': 'Shiranui Flare',    'bg': '#5bb39d', 'fg': '#fff', 'twitter':  'shiranuiflare',   'youtube': 'UCvInZx9h3jC2JzsIzoOebWg', 'bilibili': '454737600', 'retired': False},
    {'id': 42, 'name': 'Shirogane Noel',    'bg': '#dccdcd', 'fg': '#fff', 'twitter':  'shiroganenoel',   'youtube': 'UCdyqAaZDKHXg4Ahi7VENThQ', 'bilibili': '454733056', 'retired': False},
    {'id': 43, 'name': 'Uruha Rushia',      'bg': '#80d3c3', 'fg': '#fff', 'twitter':  'uruharushia',     'youtube': 'UCl_gCybOJRIgOXw6Qb4qJzQ', 'bilibili': '443300418', 'retired': True },
    {'id': 44, 'name': 'Usada Pekora',      'bg': '#acc0ee', 'fg': '#fff', 'twitter':  'usadapekora',     'youtube': 'UC1DCedRgGHBdm81E1llLhOQ', 'bilibili': '443305053', 'retired': False},

    # Japan Gen 4
    {'id': 50, 'name': 'Amane Kanata',      'bg': '#2650d0', 'fg': '#fff', 'twitter':  'amanekanatach',   'youtube': 'UCZlDXzGoo7d44bwdNObFacg', 'bilibili': '491474048', 'retired': False},
    {'id': 51, 'name': 'Himemori Luna',     'bg': '#93446d', 'fg': '#fff', 'twitter':  'himemoriluna',    'youtube': 'UCa9Y57gfeY0Zro_noHRVrnw', 'bilibili': '491474052', 'retired': False},
    {'id': 52, 'name': 'Kiryu Coco',        'bg': '#db9574', 'fg': '#fff', 'twitter':  'kiryucoco',       'youtube': 'UCS9uQI-jC3DE0L4IpXyvr6w', 'bilibili': '491474049', 'retired': True},
    {'id': 53, 'name': 'Tokoyami Towa',     'bg': '#d197ce', 'fg': '#fff', 'twitter':  'tokoyamitowa',    'youtube': 'UC1uv2Oq6kNxgATlCiez59hw', 'bilibili': '491474051', 'retired': False},
    {'id': 54, 'name': 'Tsunomaki Watame',  'bg': '#e4d3a3', 'fg': '#fff', 'twitter':  'tsunomakiwatame', 'youtube': 'UCqm3BQLlJfvkTsX_hvm0UmA', 'bilibili': '491474050', 'retired': False},

    # Jap 5th gen
    {'id': 60, 'name': 'Mano Aloe',         'bg': '#DA8EAC', 'fg': '#fff', 'twitter':  'manoaloe',        'youtube': 'UCgZuwn-O7Szh9cAgHqJ6vjw', 'bilibili': '',          'retired': True},
    {'id': 61, 'name': 'Momosuzu Nene',     'bg': '#E9D7D2', 'fg': '#fff', 'twitter':  'momosuzunene',    'youtube': 'UCAWSyEs_Io8MtpY3m-zqILA', 'bilibili': '',          'retired': False},
    {'id': 62, 'name': 'Omaru Polka',       'bg': '#37465C', 'fg': '#fff', 'twitter':  'omarupolka',      'youtube': 'UCK9V2B22uJYu3N7eR_BT9QA', 'bilibili': '',          'retired': False},
    {'id': 63, 'name': 'Shishiro Botan',    'bg': '#322C34', 'fg': '#fff', 'twitter':  'shishirobotan',   'youtube': 'UCUKD-uaobj9jiqB-VXt71mA', 'bilibili': '',          'retired': False},
    {'id': 64, 'name': 'Yukihana Lamy',     'bg': '#7895B8', 'fg': '#fff', 'twitter':  'yukihanalamy',    'youtube': 'UCFKOVgVbGmX65RxO3EtH3iw', 'bilibili': '624252706', 'retired': False},

    # Jap 6th gen (holoX)
    {'id': 120, 'name': 'La+ Darknesss',    'bg': '#403350', 'fg': '#fff', 'twitter':  'LaplusDarknesss', 'youtube': 'UCENwRMx5Yh42zWpzURebzTw', 'bilibili': '', 'retired': False},
    {'id': 121, 'name': 'Takane Lui',       'bg': '#eca3a3', 'fg': '#fff', 'twitter':  'takanelui',       'youtube': 'UCs9_O1tRPMQTHQ-N_L6FU2g', 'bilibili': '', 'retired': False},
    {'id': 122, 'name': 'Hakui Koyori',     'bg': '#d99bc9', 'fg': '#fff', 'twitter':  'hakuikoyori',     'youtube': 'UC6eWCld0KwmyHFbAqK3V-Rw', 'bilibili': '', 'retired': False},
    {'id': 123, 'name': 'Sakamata Chloe',   'bg': '#963f3f', 'fg': '#fff', 'twitter':  'sakamatachloe',   'youtube': 'UCIBY1ollUsauvVi4hW4cumw', 'bilibili': '', 'retired': False},
    {'id': 124, 'name': 'Kazama Iroha',     'bg': '#f3e3d2', 'fg': '#fff', 'twitter':  'kazamairohach',   'youtube': 'UC_vMYWcDjmfdpH6r4TTn1MQ', 'bilibili': '', 'retired': False},

    # English Myth (1st gen)
    {'id': 70, 'name': 'Ninomae Ina\'nis',  'bg': '#62567E', 'fg': '#fff', 'twitter':  'ninomaeinanis',   'youtube': 'UCMwGHR0BTZuLsmjY_NT5Pwg', 'bilibili': '', 'retired': False},
    {'id': 71, 'name': 'Gawr Gura',         'bg': '#5C81C7', 'fg': '#fff', 'twitter':  'gawrgura',        'youtube': 'UCoSrY_IQQVpmIRZ9Xf-y93g', 'bilibili': '', 'retired': False},
    {'id': 72, 'name': 'Takanashi Kiara',   'bg': '#FF511C', 'fg': '#fff', 'twitter':  'takanashikiara',  'youtube': 'UCHsx4Hqa-1ORjQTh9TYDhww', 'bilibili': '', 'retired': False},
    {'id': 73, 'name': 'Mori Calliope',     'bg': '#C90D40', 'fg': '#fff', 'twitter':  'moricalliope',    'youtube': 'UCL_qhgtOy0dy1Agp8vkySQg', 'bilibili': '', 'retired': False},
    {'id': 74, 'name': 'Watson Amelia',     'bg': '#F7DB92', 'fg': '#fff', 'twitter':  'watsonameliaen',  'youtube': 'UCyl1z3jo3XHR1riLFKG5UAg', 'bilibili': '', 'retired': False},

    # English Council (2nd gen)
    {'id': 130, 'name': 'Tsukumo Sana',     'bg': '#cf83ac', 'fg': '#fff', 'twitter':  'tsukumosana',     'youtube': 'UCsUj0dszADCGbF3gNrQEuSQ', 'bilibili': '', 'retired': False},
    {'id': 131, 'name': 'Ceres Fauna',      'bg': '#50ca61', 'fg': '#fff', 'twitter':  'ceresfauna',      'youtube': 'UCO_aKKYxn4tvrqPjcTzZ6EQ', 'bilibili': '', 'retired': False},
    {'id': 132, 'name': 'Ouro Kronii',      'bg': '#22199a', 'fg': '#fff', 'twitter':  'ourokronii',      'youtube': 'UCmbs8T6MWqUHP1tIQvSgKrg', 'bilibili': '', 'retired': False},
    {'id': 133, 'name': 'Nanashi Mumei',    'bg': '#be936f', 'fg': '#fff', 'twitter':  'nanashimumei_en', 'youtube': 'UC3n5uGu18FoCy23ggWWp8tA', 'bilibili': '', 'retired': False},
    {'id': 134, 'name': 'Hakos Baelz',      'bg': '#f33723', 'fg': '#fff', 'twitter':  'hakosbaelz',      'youtube': 'UCgmPnx-EEeOrZSg5Tiw7ZRQ', 'bilibili': '', 'retired': False},

    # VSinger (Project-hope)
    {'id': 80, 'name': 'IRyS',              'bg': '#390024', 'fg': '#fff', 'twitter': 'irys_en',          'youtube': 'UC8rcEBzJSleTkf_-agPM20g', 'bilibili': '', 'retired': False},

    # Indonesia
    {'id': 90, 'name': 'Airani Iofifteen',  'bg': '#be8b8f', 'fg': '#fff', 'twitter':  'airaniiofifteen', 'youtube': 'UCAoy6rzhSf4ydcYjJw3WoVg', 'bilibili': '', 'retired': False},
    {'id': 91, 'name': 'Ayunda Risu',       'bg': '#d48d85', 'fg': '#fff', 'twitter':  'ayunda_risu',     'youtube': 'UCOyYb1c43VlX9rc_lT6NKQw', 'bilibili': '', 'retired': False},
    {'id': 92, 'name': 'Moona Hoshinova',   'bg': '#9b85c1', 'fg': '#fff', 'twitter':  'moonahoshinova',  'youtube': 'UCP0BspO_AMEe3aQqqpo89Dg', 'bilibili': '', 'retired': False},

    # Indonesia 2nd gen
    {'id': 100, 'name': 'Kureiji Ollie',     'bg': '#E7004E', 'fg': '#fff', 'twitter':  'kureijiollie',    'youtube': 'UCYz_5n-uDuChHtLo7My1HnQ', 'bilibili': '', 'retired': False},
    {'id': 101, 'name': 'Anya Melfissa',     'bg': '#DAB75B', 'fg': '#fff', 'twitter':  'anyamelfissa',    'youtube': 'UC727SQYUvx5pDDGQpTICNWg', 'bilibili': '', 'retired': False},
    {'id': 102, 'name': 'Pavolia Reine',     'bg': '#2A64AE', 'fg': '#fff', 'twitter':  'pavoliareine',    'youtube': 'UChgTyjG-pdNvxxhdsXfHQ5Q', 'bilibili': '', 'retired': False},

    # China
    {'id': 110, 'name': 'Artia',             'bg': '#736b99', 'fg': '#fff', 'twitter':  'artia_hololive',  'youtube': '',                         'bilibili': '511613155', 'retired': True},
    {'id': 111, 'name': 'Civia',             'bg': '#67abd5', 'fg': '#fff', 'twitter':  'civia_hololive',  'youtube': 'UCgNVXGlZIFK96XdEY20sVjg', 'bilibili': '354411419', 'retired': True},
    {'id': 112, 'name': 'Doris',             'bg': '#8198c8', 'fg': '#fff', 'twitter':  'doris_hololive',  'youtube': '',                         'bilibili': '511613156', 'retired': True},
    {'id': 113, 'name': 'Rosalyn',           'bg': '#314268', 'fg': '#fff', 'twitter':  'rosalyn_holocn',  'youtube': '',                         'bilibili': '511613157', 'retired': True},
    {'id': 114, 'name': 'Spade Echo',        'bg': '#bb88a1', 'fg': '#fff', 'twitter':  'spadeecho',       'youtube': '',                         'bilibili': '456368455', 'retired': True},
    {'id': 115, 'name': 'Yogiri',            'bg': '#bd536e', 'fg': '#fff', 'twitter':  'yogiri_hololive', 'youtube': '',                         'bilibili': '427061218', 'retired': True},

    # Staff
    {'id': 1, 'name': 'Best Girl (Yagoo)', 'bg': '#C3B4AF', 'fg': '#fff', 'twitter':  'tanigox',         'youtube': 'UCu2DMOGLeR_DSStCyeQpi5Q', 'bilibili': '', 'group': 'staff', 'retired': False},
    {'id': 2, 'name': 'A-Chan',            'bg': '#413982', 'fg': '#fff', 'twitter':  'achan_uga',       'youtube': '',                         'bilibili': '', 'group': 'staff', 'retired': False},
    {'id': 3, 'name': 'Omegaα',            'bg': '#fbdeeb', 'fg': '#fff', 'twitter':  'omegaalpha_en',   'youtube': 'UCKYyiJwNg2nV7hM86U5_wvw', 'bilibili': '', 'group': 'staff', 'retired': False},

    # Official Corp Stuff
    {'id': 1, 'name': 'Japanese Branch',      'bg': '#61DFEB', 'fg': '#fff', 'twitter': 'hololivetv',  'youtube': 'UCJFZiqLMntJufDCHc6bQixg', 'bilibili': '286700005', 'group': 'corp', 'retired': False},
    {'id': 2, 'name': 'English Branch',       'bg': '#45C2F2', 'fg': '#fff', 'twitter': 'hololive_en', 'youtube': 'UCotXwY6s8pWmuWd_snKYjhg', 'bilibili': '',          'group': 'corp', 'retired': False},
    {'id': 3, 'name': 'Indonesian Branch',    'bg': '#3AAAE2', 'fg': '#fff', 'twitter': 'hololive_id', 'youtube': 'UCfrWoRGlawPQDQxxeIDRP0Q', 'bilibili': '',          'group': 'corp', 'retired': False},
    {'id': 4, 'name': 'Hololive Alternative', 'bg': '#0437BF', 'fg': '#fff', 'twitter': 'hololiveALT', 'youtube': '',                         'bilibili': '',          'group': 'corp', 'retired': False},
]

# YouTube
parts = ['statistics']
yt_key = os.environ['YOUTUBE_KEY']
yt_url = 'https://www.googleapis.com/youtube/v3/channels?part={parts}&id={channels}&key={key}'

LOG.info('Getting YouTube stats...')
ids = list(filter(None, map(lambda data: data['youtube'], channels)))
idss = [ids[:50], ids[50:]]
yt_data = {}
for ids in idss:
    yt_full_url = yt_url.format(
        parts=','.join(parts),
        channels=','.join(ids),
        key=yt_key,
    )
    yt_data.update({item['id']: item for item in requests.get(yt_full_url).json()['items']})

# Twitter
twitter_api = Api(consumer_key=os.environ['TWITTER_CONSUMER_KEY'],
                  consumer_secret=os.environ['TWITTER_CONSUMER_SECRET'],
                  access_token_key=os.environ['TWITTER_ACCESS_TOKEN'],
                  access_token_secret=os.environ['TWITTER_ACCESS_SECRET'])

LOG.info('Getting Twitter stats...')
t_data = twitter_api.GetListMembersPaged(os.environ['TWITTER_MEMBER_LIST'])[2]

images_path = BASE_PATH / 'www/profile-images/'
images_path.mkdir(parents=True, exist_ok=True)

low_poly_boy = BASE_PATH / 'triangulate-tool/build/triangulate-tool'

def is_live(channel_id: str) -> bool:
    try:
        res = requests.get(f'https://www.youtube.com/channel/{channel_id}/live', headers={
            'Cookie': 'CONSENT=YES+cb.20210328-17-p0.en-GB+FX+634; VISITOR_INFO1_LIVE=9Ovd7YuEQbw; YSC=Tnb5Btx3xik'
        })
        res.raise_for_status()
        if index := res.text.index('is_viewed_live'):
            return 'True' in res.text[index+25:index+30]
    except Exception:
        pass
    return False


def summarize_data(channel_data: dict):
    t_user = next(filter(lambda t: t.screen_name.lower() == channel_data['twitter'].lower(), t_data), None)

    if not t_user:
        LOG.fatal(f'No data found for twitter user {channel_data["name"]}')
        sys.exit(1)

    image_url = URL(t_user.profile_image_url_https.replace('_normal', ''))
    image_path = images_path / image_url.name

    if not image_path.is_file():
        LOG.info(f'Fetching new profile image for {channel_data["name"]}...')
        response = requests.get(str(image_url))
        if response.status_code == 200:
            image_path.write_bytes(response.content)
        else:
            LOG.warning('Failed to retrive image')

    channel_data['image'] = str(image_path.relative_to(BASE_PATH / 'www') if image_path.is_file() else image_url)

    channel_data['background_image'] = None
    background_image = image_path.with_stem(image_path.stem + '_background')
    if not background_image.is_file() and low_poly_boy.is_file():
        LOG.info('Generate background image')
        proc = Popen([str(low_poly_boy), str(image_path), str(background_image), '150', '10'])
        if proc.wait() != 0:
            LOG.warning('Failed to generate background image for %s', channel_data['name'])

    if background_image.is_file():
        channel_data['background_image'] = str(background_image.relative_to(BASE_PATH / 'www'))


    channel_data['t_subs'] = int(t_user.followers_count)

    b_user = None

    if channel_data['bilibili']:
        LOG.info('Getting BiliBili stats for %s...', channel_data['name'])
        b_user = UserInfo(channel_data['bilibili']).get_info()
        channel_data['b_subs'] = int(b_user['follower'])
    if channel_data['youtube']:
        channel_data['yt_subs'] = int(yt_data[channel_data['youtube']]['statistics']['subscriberCount'])

    if channel_data['youtube'] in yt_data:
        live = False
        if not channel_data['retired']:
            LOG.info('Checking if %s is live...', channel_data['name'])
            live = is_live(channel_data['youtube'])
        channel_data['is_live'] = live
        channel_data['main_subs'] = 'yt_subs'
    elif b_user:
        channel_data['main_subs'] = 'b_subs'
    else:
        channel_data['main_subs'] = 't_subs'

# Sort and gather data
with ThreadPoolExecutor(5) as executor:
    for channel_data in channels:
        executor.submit(summarize_data, channel_data)

for data in sorted(channels, reverse=True, key=lambda data: data[data['main_subs']]):
    group_name = data.get('group', 'talents')
    groups[group_name]['members'].append(data)

result = dict(sorted(groups.items(), key=lambda item: item[1]['order']))

# Write stats
data_file = BASE_PATH / 'www/stats.json'
data_file.write_text(json.dumps(groups))
LOG.info('Done')
