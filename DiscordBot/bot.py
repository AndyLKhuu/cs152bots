# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'token.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']
    perspective_key = tokens['perspective']


class ModBot(discord.Client):
    def __init__(self, key):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.messages = True

        super().__init__(command_prefix='.', intents=intents)

        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.perspective_key = key
        # self.describe_other_disinfo = ""
        self.more_details = ""
        self.level_one = ""
        self.level_two = ""
        self.level_three = ""
        self.sent = False
        self.message = ""
        self.message_author = ""

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot
        if message.author.id == self.user.id:
            # if message.content.startswith('To the best'):
            #     self.describe_other_disinfo = await client.wait_for('message', check=None)
            if message.content.startswith('Please provide more details'):
                channel = message.channel
                msg = await client.wait_for('message', check=None)
                self.more_details = msg.content
                await channel.send("We have received the following response: " + self.more_details)
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)

        if responses[0] == "ORIGINAL":
            if not self.message:
                self.message = responses[1]
                self.message_author = responses[2]
        else:
            for r in responses:
                await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            self.reports.pop(author_id)

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')

        scores = self.eval_text(message)
        await mod_channel.send(self.code_format(json.dumps(scores, indent=2)))

    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.user.id:
            return
        channel = discord.Client.get_channel(self, payload.channel_id)

        if payload.guild_id or self.sent:
            return

        if str(payload.emoji) == '1️⃣':
            self.level_one = "Harassment/Bullying"
            await channel.send("Please select the type of Harassment/Bullying:")
            options = ":regional_indicator_a: Bullying\n"
            options += ":regional_indicator_b: Sexual Harassment\n"
            options += ":regional_indicator_c: Threat\n"
            options += ":regional_indicator_d: Cyberstalking\n"
            options += ":regional_indicator_e: Hate Speech\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🇦')
            await options_msg.add_reaction('🇧')
            await options_msg.add_reaction('🇨')
            await options_msg.add_reaction('🇩')
            await options_msg.add_reaction('🇪')
        if str(payload.emoji) == '🇦':
            self.level_two = "Bullying"
        if str(payload.emoji) == '🇧':
            self.level_two = "Sexual Harassment"
        if str(payload.emoji) == '🇨':
            self.level_two = "Threat"
        if str(payload.emoji) == '🇩':
            self.level_two = "Cyberstalking"
        if str(payload.emoji) == '🇪':
            self.level_two = "Hate Speech"

        if str(payload.emoji) == '2️⃣':
            self.level_one = "False/Misleading Information"
            await channel.send("Please select the type of False/Misleading Information:")
            options = ":regional_indicator_f: Public Health\n"
            options += ":regional_indicator_g: Elections\n"
            options += ":regional_indicator_h: Politics\n"
            options += ":regional_indicator_i: Fake News/Other\n"
            # options += ":regional_indicator_j: Other\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🇫')
            await options_msg.add_reaction('🇬')
            await options_msg.add_reaction('🇭')
            await options_msg.add_reaction('🇮')
        if str(payload.emoji) == '🇫':
            self.level_two = "Public Health"
        if str(payload.emoji) == '🇬':
            self.level_two = "Elections"
        if str(payload.emoji) == '🇭':
            self.level_two = "Politics"
        if str(payload.emoji) == '🇮':
            self.level_two = "Fake News/Other"

        if str(payload.emoji) == '3️⃣':
            self.level_one = "Violence/Graphic Imagery"
            await channel.send("Please select the type of Violence/Graphic Imagery:")
            options = ":regional_indicator_k: Terrorism\n"
            options += ":regional_indicator_l: Gore\n"
            options += ":regional_indicator_m: Self-Harm/Suicide\n"
            options += ":regional_indicator_n: Sexually Explicit\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🇰')
            await options_msg.add_reaction('🇱')
            await options_msg.add_reaction('🇲')
            await options_msg.add_reaction('🇳')
        if str(payload.emoji) == '🇰':
            self.level_two = "Terrorism"
        if str(payload.emoji) == '🇱':
            self.level_two = "Gore"
        if str(payload.emoji) == '🇲':
            self.level_two = "Self-Harm/Suicide"
        if str(payload.emoji) == '🇳':
            self.level_two = "Sexually Explicit"

        if str(payload.emoji) == '4️⃣':
            self.level_one = "Spam"
            await channel.send("Please select the type of Spam:")
            options = ":regional_indicator_o: Impersonation\n"
            options += ":regional_indicator_p: Fraud/Phishing\n"
            options += ":regional_indicator_q: Solicitation\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🇴')
            await options_msg.add_reaction('🇵')
            await options_msg.add_reaction('🇶')

        if str(payload.emoji) == '🇴':
            self.level_two = "Impersonation"
        if str(payload.emoji) == '🇵':
            self.level_two = "Fraud/Phishing"
        if str(payload.emoji) == '🇶':
            self.level_two = "Solicitation"

        if str(payload.emoji) == '5️⃣':
            self.level_one = "Other"
            await channel.send("Please select the closest category to Other:")
            options = ":regional_indicator_r: Harm to Minors\n"
            options += ":regional_indicator_s: Copyright Violation\n"
            options += ":regional_indicator_t: Animal Cruelty\n"
            options += ":regional_indicator_u: Dangerous Organizations\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🇷')
            await options_msg.add_reaction('🇸')
            await options_msg.add_reaction('🇹')
            await options_msg.add_reaction('🇺')
        if str(payload.emoji) == '🇷':
            self.level_two = "Harm to Minors"
        if str(payload.emoji) == '🇸':
            self.level_two = "Copyright Violation"
        if str(payload.emoji) == '🇹':
            self.level_two = "Animal Cruelty"
        if str(payload.emoji) == '🇺':
            self.level_two = "Dangerous Organizations"

        false_info = ['🇫', '🇬', '🇭', '🇮', '🇯']
        if str(payload.emoji) in false_info:
            await channel.send("Please choose the option that best describes "
                               "the type of false information you are reporting:")
            options = ":arrow_left: Purposefully falsified information for " \
                      "obvious political, financial, or other gains.\n"
            options += ":arrow_right: False information due to suspected hacking, or unintentional false information\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('⬅️')
            await options_msg.add_reaction('➡️')
        if str(payload.emoji) == '⬅️':
            self.level_three = "Purposefully falsified information for " \
                      "obvious political, financial, or other gains."
        if str(payload.emoji) == '➡️':
            self.level_three = "False information due to suspected hacking, or unintentional false information\n"

        targeted = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹', '🇺', '⬅️','➡️']
        if str(payload.emoji) in targeted:
            await channel.send("Would you like to provide more details on how the content violates the community "
                               "guidelines?")
            options = ":white_check_mark: Yes\n"
            options += ":x: No\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('✅')
            await options_msg.add_reaction('❌')

        if str(payload.emoji) == '✅':
            await channel.send("Please provide more details on how the content violates the community guidelines.")
            await client.wait_for('message', check=None)

        if str(payload.emoji) == '❌':
            self.level_three = "N/A"

        if str(payload.emoji) == '❌' or str(payload.emoji) == '✅':
            await channel.send("Would you like to block this user?")
            options = ":no_entry_sign: Yes\n"
            options += ":o: No\n"
            options_msg = await channel.send(options)
            await options_msg.add_reaction('🚫')
            await options_msg.add_reaction('⭕')

        if str(payload.emoji) == '🚫':
            await channel.send("The user has been blocked.")
        if str(payload.emoji) == '⭕' or str(payload.emoji) == '🚫':
            await channel.send("We appreciate you taking the time to help us uphold the community guidelines. "
                               "Our team will take the appropriate action, which may result in the "
                               "content or account removal.")

            for guild in self.guilds:
                for channel in guild.text_channels:
                    if channel.name == f'group-{self.group_num}-mod':
                        await channel.send(f'Forwarded message (from user report):\nOriginal author: '
                                           f'{self.message_author}\nOriginal content: "'
                                           f'{self.message}"\nUserID of Reporter: '
                                           f'{payload.user_id}\nPrimary Abuse Type: "'
                                           f'{self.level_one}"\nCategory of Abuse Type: "'
                                           f'{self.level_two}"\nDisinformation Type: "'
                                           f'{self.level_three}"\nMore Details from User: "'
                                           f'{self.more_details}"')
                        self.sent = True

    async def on_raw_message_edit(self, payload):
        channel = discord.Client.get_channel(self, payload.channel_id)
        new_msg = await channel.fetch_message(payload.message_id)
        if not self.sent:
            await channel.send("We have received your edited response: " + new_msg.content)
            self.more_details = new_msg.content
        else:
            await channel.send("Sorry, we cannot process your edited response because the report has already "
                               "been sent to the moderators. Please submit another report with your edited response.")

    def eval_text(self, message):
        '''
        Given a message, forwards the message to Perspective and returns a dictionary of scores.
        '''
        PERSPECTIVE_URL = 'https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze'

        url = PERSPECTIVE_URL + '?key=' + self.perspective_key
        data_dict = {
            'comment': {'text': message.content},
            'languages': ['en'],
            'requestedAttributes': {
                                    'SEVERE_TOXICITY': {}, 'PROFANITY': {},
                                    'IDENTITY_ATTACK': {}, 'THREAT': {},
                                    'TOXICITY': {}, 'FLIRTATION': {}
                                },
            'doNotStore': True
        }
        response = requests.post(url, data=json.dumps(data_dict))
        response_dict = response.json()

        scores = {}
        for attr in response_dict["attributeScores"]:
            scores[attr] = response_dict["attributeScores"][attr]["summaryScore"]["value"]

        return scores

    def code_format(self, text):
        return "```" + text + "```"


client = ModBot(perspective_key)
client.run(discord_token)
