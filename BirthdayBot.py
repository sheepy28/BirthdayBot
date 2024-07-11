import discord
from discord import app_commands
from discord.ext import tasks
import datetime
import json
import random
import pytz
from collections import Counter

intents = discord.Intents.default()
intents.members = True

class BirthdayBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.birthdays = self.load_birthdays()
        self.birthday_messages = [
            "Happy Birthday, {member}! 🎉🎂",
            "It's {member}'s special day! Happy Birthday! 🥳🎈",
            "Wishing you a wonderful birthday, {member}! 🎊🍰",
            "Happy Birthday to {member}! 🎁😄"
        ]

    async def setup_hook(self):
        await self.tree.sync()

    def load_birthdays(self):
        try:
            with open('birthdays.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_birthdays(self):
        with open('birthdays.json', 'w') as f:
            json.dump(self.birthdays, f)

bot = BirthdayBot()

class BirthdayView(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.value = None

    @discord.ui.button(label="Set Birthday", style=discord.ButtonStyle.primary)
    async def set_birthday(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal(self.bot))

    @discord.ui.button(label="Remove Birthday", style=discord.ButtonStyle.danger)
    async def remove_birthday(self, interaction: discord.Interaction, button: discord.ui.Button):
        member_id = str(interaction.user.id)
        if member_id in self.bot.birthdays:
            del self.bot.birthdays[member_id]
            self.bot.save_birthdays()
            await interaction.response.send_message("Your birthday has been removed.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have a birthday set.", ephemeral=True)

class BirthdayModal(discord.ui.Modal, title="Set Your Birthday"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    birthday = discord.ui.TextInput(
        label="Enter your birthday (DD/MM or DD/MM/YY)",
        placeholder="e.g., 15/03 or 15/03/90",
        required=True,
        max_length=8
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date = self.birthday.value
            try:
                birthday = datetime.datetime.strptime(date, '%d/%m/%y').date()
                birthday_str = birthday.strftime('%d/%m/%y')
            except ValueError:
                birthday = datetime.datetime.strptime(date, '%d/%m').date()
                birthday_str = birthday.strftime('%d/%m')
            
            member_id = str(interaction.user.id)
            self.bot.birthdays[member_id] = birthday_str
            self.bot.save_birthdays()
            await interaction.response.send_message(f"Your birthday has been set to {birthday_str}", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid date format. Please use DD/MM or DD/MM/YY.", ephemeral=True)

@bot.tree.command(name="birthday", description="Manage your birthday")
async def birthday(interaction: discord.Interaction):
    view = BirthdayView(bot)
    await interaction.response.send_message("What would you like to do?", view=view, ephemeral=True)

@bot.tree.command(name="birthdaylist", description="List all registered birthdays")
async def birthday_list(interaction: discord.Interaction):
    if not bot.birthdays:
        await interaction.response.send_message("No birthdays have been registered yet.", ephemeral=True)
        return

    birthday_entries = []
    for member_id, birthday_str in bot.birthdays.items():
        member = interaction.guild.get_member(int(member_id))
        if member:
            username = member.name
        else:
            username = f"Unknown User (ID: {member_id})"
        birthday_entries.append(f"{username}: {birthday_str}")

    birthday_entries.sort()  # Sort alphabetically by username

    message = "Registered birthdays:\n"
    message += "\n".join(birthday_entries)

    # If the message is too long, split it into multiple messages
    if len(message) > 2000:
        messages = []
        while len(message) > 2000:
            split_index = message.rfind('\n', 0, 2000)
            messages.append(message[:split_index])
            message = message[split_index+1:]
        messages.append(message)

        await interaction.response.send_message(messages[0])
        for msg in messages[1:]:
            await interaction.channel.send(msg)
    else:
        await interaction.response.send_message(message)

@bot.tree.command(name="birthdaystats", description="Show birthday statistics")
async def birthday_stats(interaction: discord.Interaction):
    months = Counter()
    for birthday in bot.birthdays.values():
        month = int(birthday.split('/')[1])
        months[month] += 1
    
    most_common = months.most_common(1)
    if most_common:
        most_common_month = datetime.date(1900, most_common[0][0], 1).strftime('%B')
        message = f"Birthday statistics:\n"
        message += f"Total birthdays registered: {len(bot.birthdays)}\n"
        message += f"Most common birth month: {most_common_month} ({most_common[0][1]} birthdays)"
    else:
        message = "No birthdays have been registered yet."
    
    await interaction.response.send_message(message)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    check_birthdays.start()

@tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=pytz.UTC))
async def check_birthdays():
    today = datetime.datetime.now(pytz.UTC).date()
    for guild in bot.guilds:
        for member_id, birthday_str in bot.birthdays.items():
            try:
                birthday = datetime.datetime.strptime(birthday_str, '%d/%m/%y').date()
            except ValueError:
                birthday = datetime.datetime.strptime(birthday_str, '%d/%m').date()
            
            if birthday.month == today.month and birthday.day == today.day:
                member = guild.get_member(int(member_id))
                if member:
                    channel = guild.system_channel or guild.text_channels[0]
                    message = random.choice(bot.birthday_messages).format(member=member.mention)
                    try:
                        await channel.send(message)
                    except discord.errors.Forbidden:
                        print(f"Unable to send birthday message in guild {guild.name} (ID: {guild.id})")
                        continue

                    # Add birthday role
                    birthday_role = discord.utils.get(guild.roles, name="Happy Birthday")
                    if not birthday_role:
                        try:
                            birthday_role = await guild.create_role(name="Happy Birthday", colour=discord.Colour.gold())
                        except discord.errors.Forbidden:
                            print(f"Unable to create 'Happy Birthday' role in guild {guild.name} (ID: {guild.id})")
                            continue

                    if birthday_role:
                        try:
                            await member.add_roles(birthday_role)
                        except discord.errors.Forbidden:
                            print(f"Unable to add 'Happy Birthday' role to {member.name} in guild {guild.name} (ID: {guild.id})")
    
    # Remove birthday role from yesterday's birthday people
    yesterday = today - datetime.timedelta(days=1)
    for guild in bot.guilds:
        birthday_role = discord.utils.get(guild.roles, name="Happy Birthday")
        if birthday_role:
            for member in birthday_role.members:
                try:
                    await member.remove_roles(birthday_role)
                except discord.errors.Forbidden:
                    print(f"Unable to remove 'Happy Birthday' role from {member.name} in guild {guild.name} (ID: {guild.id})")

@check_birthdays.before_loop
async def before_check_birthdays():
    await bot.wait_until_ready()

@bot.tree.command(name="checkbirthdays", description="Manually trigger birthday checks")
@app_commands.checks.has_permissions(administrator=True)
async def manual_check_birthdays(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await check_birthdays()
    await interaction.followup.send("Birthday check completed.", ephemeral=True)

@bot.tree.command(name="testbirthday", description="Test the birthday message for a user")
@app_commands.describe(member="The member to test the birthday message for")
async def test_birthday(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    
    # Check if the bot has permission to send messages in the channel
    if not channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.response.send_message("I don't have permission to send messages in that channel.", ephemeral=True)
        return

    message = random.choice(bot.birthday_messages).format(member=member.mention)
    
    try:
        await channel.send(message)
    except discord.errors.Forbidden:
        await interaction.response.send_message("I don't have permission to send messages in that channel.", ephemeral=True)
        return

    # Check if the bot has permission to manage roles
    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("Birthday message sent, but I don't have permission to manage roles.", ephemeral=True)
        return

    # Assign birthday role for testing
    try:
        birthday_role = discord.utils.get(interaction.guild.roles, name="Happy Birthday")
        if birthday_role:
            await member.add_roles(birthday_role)
        else:
            birthday_role = await interaction.guild.create_role(name="Happy Birthday", colour=discord.Colour.gold())
            await member.add_roles(birthday_role)
    except discord.errors.Forbidden:
        await interaction.response.send_message("Birthday message sent, but I don't have permission to manage roles.", ephemeral=True)
        return

    await interaction.response.send_message(f"Birthday message sent for {member.name} and role assigned.", ephemeral=True)

bot.run('MTI2MDY5NTI5MTY5MTEzOTE2Mw.GNdNyB.Dq5YhZKFCzun2M5RpSnz8jqRyLI8N26rbdKe8M')