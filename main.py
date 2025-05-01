import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, button
from discord import TextStyle
import json
import os
import traceback
import datetime
import asyncio

TOKEN = '' # TOKEN
if not TOKEN or len(TOKEN) < 55:
    print("BŁĄD KRYTYCZNY: Brak tokenu bota lub jest on nieprawidłowy! Sprawdź wartość TOKEN.")
    exit()

try:
    GUILD_ID = int(os.getenv('GUILD_ID', '')) # SERVER ID into ' '
except ValueError:
    print("BŁĄD KRYTYCZNY: GUILD_ID musi być liczbą całkowitą!")
    exit()

PLACEHOLDER_GUILD_ID = 123456789012345678
if GUILD_ID == PLACEHOLDER_GUILD_ID:
    print("="*40 + "\n BŁĄD KRYTYCZNY: ID serwera (GUILD_ID) jest ustawione na wartość domyślną placeholder! \n" + "="*40)
    exit()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- JSON ---
CONFIG_FILE = 'ticket_config.json'
default_config_structure = {
    'ticket_categories': {},        # { 'typ_ticketa': 'id_kategorii_str', 'zamkniete': 'id_kategorii_str' }
    'ticket_roles': {},             # { 'nazwa_roli': 'id_roli_str' } np. {'aiad': '123'}
    'ticket_role_mapping': {},      # { 'typ_ticketa': ['typ_ticketu', 'nazwa_roli'] } np. {'aiad': ['aiad']}
    'ticket_panel_channel_id': None,# 'id_kanalu_str'
    'ticket_panel_message_id': None,# 'id_wiadomosci_str'
    'ticket_counters': {},          # { 'typ_ticketa': ostatni_numer_int }
    'ticket_creators': {},          # { 'id_kanalu_str': {'user_id': id_tworcy_int, 'type': 'typ_ticketa_str', 'welcome_msg_id': id_wiadomosci_int | None} }
    'closure_requests': {},         # { 'id_kanalu_str': 'iso_timestamp_str' }
    'role_reaction_message_id': None
}
config = default_config_structure.copy()

def load_config():
    global config
    config = default_config_structure.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                for key in default_config_structure:
                    config[key] = loaded_config.get(key, default_config_structure[key])
                print(f"INFO: Config załadowany poprawnie z {CONFIG_FILE}")

                needs_resave = False
                migrated_creators = {}
                if isinstance(config.get('ticket_creators'), dict):
                    for ch_id, creator_info in config['ticket_creators'].items():
                        if isinstance(creator_info, int) or (isinstance(creator_info, dict) and 'welcome_msg_id' not in creator_info):
                            old_user_id = creator_info if isinstance(creator_info, int) else creator_info.get('user_id')
                            old_type = 'unknown' if isinstance(creator_info, int) else creator_info.get('type', 'unknown')
                            if old_user_id and isinstance(old_user_id, int):
                                print(f"[MIGRACJA] Konwersja starego formatu ticket_creators dla kanału {ch_id}.")
                                migrated_creators[ch_id] = {'user_id': old_user_id, 'type': old_type or 'unknown', 'welcome_msg_id': None}
                                needs_resave = True
                            else:
                                print(f"[BŁĄD MIGRACJI] Nieprawidłowy stary format (brak/złe user_id) dla kanału {ch_id}: {creator_info}. Pomijanie.")
                        elif isinstance(creator_info, dict) and 'user_id' in creator_info and isinstance(creator_info.get('user_id'), int) and 'welcome_msg_id' in creator_info:
                            migrated_creators[ch_id] = creator_info
                        else:
                            print(f"[BŁĄD FORMATU] Nieprawidłowy wpis ticket_creators dla kanału {ch_id}: {creator_info}. Pomijanie.")
                else:
                    print("[OSTRZEŻENIE] Sekcja 'ticket_creators' w configu nie jest słownikiem. Resetowanie do pustego.")
                    config['ticket_creators'] = {}
                    needs_resave = True

                if needs_resave:
                    config['ticket_creators'] = migrated_creators
                    print("INFO: Zakończono migrację formatu ticket_creators. Zapisywanie zmian...")
                    save_config()

        except json.JSONDecodeError as e:
            print(f"BŁĄD KRYTYCZNY: Błąd dekodowania JSON w {CONFIG_FILE}: {e}. Używam domyślnego configu.")
            config = default_config_structure.copy()
        except Exception as e:
            print(f"BŁĄD KRYTYCZNY: Nieoczekiwany błąd podczas odczytu {CONFIG_FILE}: {e}. Używam domyślnego configu.")
            traceback.print_exc()
            config = default_config_structure.copy()
    else:
        print(f"INFO: Plik konfiguracyjny {CONFIG_FILE} nie istnieje. Używam domyślnego configu. Zostanie utworzony przy pierwszym zapisie.")

def save_config():
    global config
    try:
        config_to_save = config.copy()
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=4, ensure_ascii=False, sort_keys=True)
    except Exception as e:
        print(f"BŁĄD KRYTYCZNY: Nie udało się zapisać configu do {CONFIG_FILE}: {e}")
        traceback.print_exc()

@bot.tree.command(name="get_role", description="Wysyła wiadomość do odbierania roli Kadet/LSPD.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(administrator=True)
async def send_role_reaction_message(interaction: discord.Interaction):
    global config
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Ta komenda może być użyta tylko na kanale tekstowym.", ephemeral=True)
        return

    perms = channel.permissions_for(interaction.guild.me)
    if not perms.send_messages or not perms.embed_links or not perms.add_reactions or not perms.manage_roles:
         await interaction.response.send_message(
             "Bot potrzebuje uprawnień: Wyślij wiadomości, Osadź linki, Dodaj reakcje, Zarządzaj rolami.",
             ephemeral=True
         )
         return

    await interaction.response.defer(ephemeral=True, thinking=True)

    embed = discord.Embed(
        title="Odbierz Role",
        description="W celu odebrania roli **Kadet** i **LSPD** kliknij reakcję :white_check_mark: poniżej.",
        color=discord.Color.blue()
    )

    try:
        message = await channel.send(embed=embed)
        await message.add_reaction("✅")

        config['role_reaction_message_id'] = message.id
        save_config()

        print(f"INFO: Wysłano wiadomość do odbierania ról ({message.id}) na kanale {channel.name} ({channel.id})")
        await interaction.followup.send(f"Wysłano wiadomość do odbierania ról na kanale {channel.mention}.", ephemeral=True)

    except discord.Forbidden:
        print(f"BŁĄD: Brak uprawnień do wysłania wiadomości lub dodania reakcji na kanale {channel.name}")
        await interaction.followup.send("Wystąpił błąd uprawnień podczas wysyłania wiadomości lub dodawania reakcji.", ephemeral=True)
    except Exception as e:
        print(f"BŁĄD: Nieoczekiwany błąd podczas wysyłania wiadomości /odbierz_role: {e}")
        traceback.print_exc()
        await interaction.followup.send("Wystąpił nieoczekiwany błąd.", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    global config
    if payload.user_id == bot.user.id:
        return

    role_message_id = config.get('role_reaction_message_id')
    if not role_message_id or payload.message_id != role_message_id:
        return

    target_emoji = "✅"
    if str(payload.emoji) == target_emoji:
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            print(f"[BŁĄD Reaction Role] Nie znaleziono serwera: {payload.guild_id}")
            return

        member = guild.get_member(payload.user_id)
        if not member:
            print(f"[INFO Reaction Role] Nie znaleziono członka w cache: {payload.user_id}, próba fetch...")
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.NotFound:
                print(f"[BŁĄD Reaction Role] Nie znaleziono członka po fetch: {payload.user_id}")
                return
            except discord.HTTPException as e:
                 print(f"[BŁĄD Reaction Role] Błąd HTTP przy fetch member {payload.user_id}: {e}")
                 return
            except Exception as e:
                 print(f"[BŁĄD Reaction Role] Nieoczekiwany błąd przy fetch member {payload.user_id}: {e}")
                 return

        kadet_role_id = 1292954326687420458
        lspd_role_id = 1292918945292226664

        role_kadet = guild.get_role(kadet_role_id)
        role_lspd = guild.get_role(lspd_role_id)

        roles_to_add = []
        if role_kadet: roles_to_add.append(role_kadet)
        else: print(f"[BŁĄD Reaction Role] Nie znaleziono roli Kadet o ID: {kadet_role_id}")
        if role_lspd: roles_to_add.append(role_lspd)
        else: print(f"[BŁĄD Reaction Role] Nie znaleziono roli LSPD o ID: {lspd_role_id}")

        if not roles_to_add:
            print("[BŁĄD Reaction Role] Żadna z docelowych ról nie została znaleziona na serwerze.")
            return

        try:
            await member.add_roles(*roles_to_add, reason=f"Automatyczne nadanie roli przez reakcję na wiadomości {payload.message_id}")
            print(f"INFO: Nadano role {[r.name for r in roles_to_add]} użytkownikowi {member.display_name} ({member.id})")

            try:
                 await member.send(f"Otrzymałeś role: {', '.join([r.name for r in roles_to_add])} na serwerze {guild.name}.")
            except discord.Forbidden:
                 print(f"INFO: Nie można wysłać DM do {member.display_name} - zablokowane DM?")

        except discord.Forbidden:
            print(f"[BŁĄD Reaction Role] Bot nie ma uprawnień do nadania ról {member.display_name}")
        except discord.HTTPException as e:
             print(f"[BŁĄD Reaction Role] Błąd HTTP podczas nadawania ról {member.display_name}: {e}")
        except Exception as e:
            print(f"[BŁĄD Reaction Role] Nieoczekiwany błąd podczas nadawania ról {member.display_name}: {e}")
            traceback.print_exc()
        finally:
            try:
                channel = guild.get_channel(payload.channel_id)
                if isinstance(channel, discord.TextChannel):
                    message = await channel.fetch_message(payload.message_id)
                    await message.remove_reaction(payload.emoji, member)
            except discord.NotFound:
                print(f"INFO: Nie znaleziono wiadomości {payload.message_id} lub reakcji do usunięcia.")
            except discord.Forbidden:
                print(f"BŁĄD: Brak uprawnień do usunięcia reakcji użytkownika {member.id} z wiadomości {payload.message_id}")
            except Exception as e:
                print(f"BŁĄD: Nieoczekiwany błąd podczas usuwania reakcji: {e}")

    elif str(payload.emoji) != target_emoji:
        try:
            guild = bot.get_guild(payload.guild_id)
            if not guild: return
            member = guild.get_member(payload.user_id)
            if not member: member = await guild.fetch_member(payload.user_id)

            channel = guild.get_channel(payload.channel_id)
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, member)
                print(f"INFO: Usunięto niepoprawną reakcję '{payload.emoji}' od {member.display_name} z wiadomości {payload.message_id}")

        except discord.NotFound: pass
        except discord.Forbidden: print(f"BŁĄD: Brak uprawnień do usunięcia reakcji '{payload.emoji}' od użytkownika {payload.user_id}")
        except Exception as e: print(f"BŁĄD: Usuwanie niepoprawnej reakcji: {e}")

@send_role_reaction_message.error
async def send_role_reaction_message_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("Nie masz uprawnień (Administrator) do użycia tej komendy.", ephemeral=True)
    else:
        print(f"Błąd w komendzie /odbierz_role: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("Wystąpił błąd podczas wykonywania komendy.", ephemeral=True)
        else:
            await interaction.followup.send("Wystąpił błąd podczas wykonywania komendy.", ephemeral=True)

class TicketActionView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Zamknij Ticket", style=discord.ButtonStyle.danger, custom_id="persistent_view_close_ticket")
    async def close_ticket_button(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        user = interaction.user

        if not isinstance(channel, discord.TextChannel):
             await interaction.response.send_message("Błąd: To nie jest kanał tekstowy.", ephemeral=True); return

        ticket_creators = config.get('ticket_creators', {})
        creator_data = ticket_creators.get(str(channel.id))
        is_creator = False
        if creator_data and isinstance(creator_data, dict): is_creator = (creator_data.get('user_id') == user.id)
        has_manage_channels_perm = channel.permissions_for(user).manage_channels

        if not is_creator and not has_manage_channels_perm:
            await interaction.response.send_message("Nie jesteś twórcą ticketa ani nie masz uprawnień, by go zamknąć.", ephemeral=True); return

        closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
        closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
        if closed_category_id and channel.category_id == closed_category_id:
            await interaction.response.send_message("Ten ticket jest już zamknięty.", ephemeral=True); return

        confirm_view = ConfirmCloseView(original_user_id=user.id)
        await interaction.response.send_message("Czy na pewno chcesz zamknąć ten ticket?", view=confirm_view, ephemeral=True)
        confirm_view.message_to_edit = await interaction.original_response()

        await confirm_view.wait()

        print(f"[INFO] ConfirmCloseView zakończony dla {channel.id}. Wynik: {confirm_view.confirmed_action}")


    @button(label="Poproś o Zamknięcie", style=discord.ButtonStyle.secondary, custom_id="persistent_view_request_closure")
    async def request_closure_button(self, interaction: discord.Interaction, button: Button):
        channel = interaction.channel
        user = interaction.user
        guild = interaction.guild
        channel_id_str = str(channel.id)

        if not isinstance(channel, discord.TextChannel):
             await interaction.response.send_message("Błąd: To nie jest kanał tekstowy.", ephemeral=True); return

        closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
        closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
        if closed_category_id and channel.category_id == closed_category_id:
            await interaction.response.send_message("Ten ticket jest już zamknięty.", ephemeral=True); return

        ticket_creators = config.get('ticket_creators', {})
        creator_data = ticket_creators.get(channel_id_str)

        if not creator_data or not isinstance(creator_data, dict) or 'user_id' not in creator_data:
            await interaction.response.send_message("Błąd: Nie można znaleźć danych twórcy tego ticketa w konfiguracji.", ephemeral=True); return

        creator_id = creator_data.get('user_id')

        if interaction.user.id == creator_id:
             await interaction.response.send_message("Jesteś twórcą tego ticketa. Możesz go zamknąć samodzielnie.", ephemeral=True); return

        if channel_id_str in config.get('closure_requests', {}):
             await interaction.response.send_message("Prośba o zamknięcie tego ticketa została już wysłana.", ephemeral=True); return

        creator = guild.get_member(creator_id)
        if not creator:
            try:
                print(f"[Request Closure] Cache miss dla twórcy {creator_id}, próba fetch...")
                creator = await guild.fetch_member(creator_id)
            except (discord.NotFound, discord.HTTPException) as e:
                await interaction.response.send_message(f"Nie można znaleźć twórcy tego ticketa na serwerze (ID: {creator_id}). Błąd: {e}", ephemeral=True); return
            except Exception as e:
                 print(f"[BŁĄD] Request Closure fetch member {creator_id}: {e}")
                 await interaction.response.send_message("Błąd serwera podczas wyszukiwania twórcy.", ephemeral=True); return

        now_iso = discord.utils.utcnow().isoformat()
        config.setdefault('closure_requests', {})[channel_id_str] = now_iso
        save_config()
        print(f"INFO: Zapisano prośbę o zamknięcie dla kanału {channel_id_str} o czasie {now_iso}")

        try:
            await channel.send(f"{creator.mention}, użytkownik {user.mention} prosi o zamknięcie tego ticketa.")
            await interaction.response.send_message("Wysłano prośbę o zamknięcie do twórcy ticketa.", ephemeral=True)
        except discord.Forbidden:
             config.get('closure_requests', {}).pop(channel_id_str, None); save_config()
             await interaction.response.send_message("Błąd: Bot nie ma uprawnień do wysyłania wiadomości na tym kanale.", ephemeral=True)
        except Exception as e:
            config.get('closure_requests', {}).pop(channel_id_str, None); save_config()
            print(f"BŁĄD: Wysyłanie prośby o zamknięcie w kanale {channel_id_str}: {e}")
            await interaction.response.send_message("Nie udało się wysłać prośby o zamknięcie.", ephemeral=True)

class ConfirmCloseView(View):
    def __init__(self, original_user_id: int, *, timeout=120):
        super().__init__(timeout=timeout)
        self.confirmed_action : bool | None = None
        self.message_to_edit : discord.InteractionMessage | None = None
        self.original_user_id = original_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
            await interaction.response.send_message("Tylko osoba, która zainicjowała zamknięcie, może je potwierdzić.", ephemeral=True)
            return False
        return True

    @button(label="Potwierdź Zamknięcie", style=discord.ButtonStyle.danger, custom_id="confirm_close_action_internal")
    async def confirm_button_callback(self, interaction: discord.Interaction, button_obj: Button):
        channel = interaction.channel
        user = interaction.user
        guild = interaction.guild

        if not isinstance(channel, discord.TextChannel):
             await interaction.response.edit_message(content="Błąd: Kanał nie jest tekstowy?", view=None); self.stop(); return

        ticket_creators = config.get('ticket_creators', {})
        creator_data = ticket_creators.get(str(channel.id))
        is_creator = False
        if creator_data and isinstance(creator_data, dict): is_creator = (creator_data.get('user_id') == user.id)
        has_manage_channels_perm = channel.permissions_for(user).manage_channels

        if not is_creator and not has_manage_channels_perm:
            await interaction.response.edit_message(content="Wygląda na to, że nie masz już uprawnień do zamknięcia tego ticketa.", view=None)
            self.confirmed_action = False; self.stop(); return

        try:
            await interaction.response.edit_message(content="Potwierdzono. Zamykanie ticketa...", view=None)
        except discord.NotFound:
             print(f"[OSTRZEŻENIE] ConfirmCloseView: Nie udało się edytować wiadomości potwierdzenia (wygasła?) w kanale {channel.id}")
             try: await interaction.followup.send("Potwierdzono. Zamykanie ticketa...", ephemeral=True)
             except Exception as e_followup: print(f"Błąd wysyłania followup w ConfirmCloseView: {e_followup}")
        except Exception as e_edit:
             print(f"[BŁĄD] ConfirmCloseView: Edycja wiadomości potwierdzenia: {e_edit}")

        success, message = await _internal_close_ticket(channel, guild, user, reason="Zamknięto przez potwierdzenie przyciskiem")

        try:
            if self.message_to_edit and not self.message_to_edit.is_expired():
                await self.message_to_edit.edit(content=f"Wynik zamykania ticketa:\n{message}", view=None)
            elif not interaction.is_expired():
                 await interaction.followup.send(f"Wynik zamykania ticketa:\n{message}", ephemeral=True)
            else:
                 print(f"INFO: ConfirmCloseView: Nie można wysłać wyniku zamknięcia dla {channel.id} (interakcja wygasła).")
        except discord.NotFound:
             print(f"INFO: ConfirmCloseView: Nie można edytować wiadomości po zamknięciu (wygasła?).")
             if not interaction.is_expired(): await interaction.followup.send(f"Wynik zamykania ticketa:\n{message}", ephemeral=True)
        except Exception as e_final_edit:
             print(f"[BŁĄD] ConfirmCloseView: Edycja wiadomości/followup po zamknięciu: {e_final_edit}")

        self.confirmed_action = success
        self.stop()

    @button(label="Anuluj", style=discord.ButtonStyle.secondary, custom_id="cancel_close_action_internal")
    async def cancel_button_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Anulowano zamykanie ticketa.", view=None)
        self.confirmed_action = False
        self.stop()

    async def on_timeout(self):
        print(f"INFO: Widok ConfirmCloseView dla użytkownika {self.original_user_id} wygasł.")
        if self.message_to_edit and not self.message_to_edit.is_expired():
             try:
                 await self.message_to_edit.edit(content="Czas na potwierdzenie zamknięcia minął.", view=None)
             except Exception as e: print(f"BŁĄD: Edycja wiad. ConfirmCloseView po timeout: {e}")
        self.confirmed_action = None
        self.stop()


class ConfirmationView(discord.ui.View):
    def __init__(self, original_interaction: discord.Interaction, powod: str | None, *, timeout=60.0):
        super().__init__(timeout=timeout)
        self.original_interaction = original_interaction
        self.powod = powod
        self.message : discord.InteractionMessage | None = None

    async def on_timeout(self):
        if self.message and not self.message.is_expired():
            try:
                for item in self.children: item.disabled = True
                await self.message.edit(content="Potwierdzenie zamknięcia ticketa (/close) wygasło.", view=self)
            except discord.NotFound: pass
            except Exception as e: print(f"[BŁĄD] ConfirmationView (/close) on_timeout edit: {e}")
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_interaction.user.id:
            await interaction.response.send_message("Tylko osoba, która użyła komendy /close może potwierdzić.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Tak, zamknij", style=discord.ButtonStyle.danger, custom_id="confirm_close_slash")
    async def yes_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)

        for item in self.children: item.disabled = True
        try:
            if self.message and not self.message.is_expired():
                 await self.message.edit(content=f"Potwierdzono przez {interaction.user.mention}. Zamykanie ticketa...", view=self)
        except discord.NotFound: pass
        except Exception as e_edit: print(f"[OSTRZEŻENIE] ConfirmationView (/close) yes_callback edit message: {e_edit}")

        channel = self.original_interaction.channel
        guild = self.original_interaction.guild
        user = self.original_interaction.user
        powod = self.powod

        print(f"\n--- Rozpoczęto zamykanie po potwierdzeniu (/close): Kanał ID: {channel.id}, przez: {user.name} ({user.id}) ---")

        success, summary_message = await _internal_close_ticket(channel, guild, user, reason=powod or "Zamknięto komendą /close")

        try:
            await interaction.followup.send(f"Wynik operacji zamknięcia ticketa:\n{summary_message}", ephemeral=True)
        except Exception as e_followup:
            print(f"[BŁĄD KRYTYCZNY] ConfirmationView (/close) yes_callback followup: {e_followup}")

        print(f"--- Zakończono przetwarzanie po potwierdzeniu /close: Kanał ID: {channel.id}. Sukces: {success} ---")
        self.stop()


    @discord.ui.button(label="Nie, anuluj", style=discord.ButtonStyle.secondary, custom_id="cancel_close_slash")
    async def no_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(content="Zamykanie ticketa anulowane.", view=None)
        print(f"[INFO] /close Anulowano [{self.original_interaction.channel.id}]: Przez {interaction.user.name}")
        self.stop()

class ConfirmButton(Button):
    def __init__(self, ticket_type: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ticket_type = ticket_type

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        global config
        guild = interaction.guild
        user = interaction.user

        category_id_str = config.get('ticket_categories', {}).get(self.ticket_type)
        closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")

        category_id = None
        if category_id_str and category_id_str.isdigit(): category_id = int(category_id_str)
        else: await interaction.followup.send(f"ID kategorii dla typu '{self.ticket_type}' jest niepoprawne/nieustawione.", ephemeral=True); return

        closed_category_id = None
        if closed_category_id_str and closed_category_id_str.isdigit(): closed_category_id = int(closed_category_id_str)

        if category_id == closed_category_id:
             await interaction.followup.send("Nie można tworzyć ticketów w kategorii 'Zamknięte'.", ephemeral=True); return

        role_ids_to_mention = []
        roles_to_grant_perms = []
        role_mapping_for_type = config.get('ticket_role_mapping', {}).get(self.ticket_type, [])
        all_ticket_roles = config.get('ticket_roles', {})

        for role_name in role_mapping_for_type:
            role_id_str = all_ticket_roles.get(role_name)
            if role_id_str and role_id_str.isdigit():
                role_id = int(role_id_str)
                role = guild.get_role(role_id)
                if role: role_ids_to_mention.append(str(role_id)); roles_to_grant_perms.append(role)
                else: print(f"[OSTRZEŻENIE] Create Ticket: Rola '{role_name}' (ID:{role_id}) nie znaleziona.")
            else: print(f"[OSTRZEŻENIE] Create Ticket: Nieprawidłowe/brakujące ID dla roli '{role_name}' w configu.")

        mention_string = ' '.join([f"<@&{role_id}>" for role_id in role_ids_to_mention]) if role_ids_to_mention else ""

        ticket_channel = None; category = None; ticket_number = 0; welcome_msg = None
        try:
            category = guild.get_channel(category_id)
            if not category: category = await guild.fetch_channel(category_id)

            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(f"ID ({category_id}) dla '{self.ticket_type}' nie jest kategorią.", ephemeral=True); return

            counters = config.setdefault('ticket_counters', {})
            counters[self.ticket_type] = counters.get(self.ticket_type, 0) + 1
            ticket_number = counters[self.ticket_type]

            user_name_pure = user.display_name
            user_name_split = user_name_pure.replace(' ', '-')

            user_name_safe = "".join(c for c in user_name_split if c.isalnum() or c in ('-', '_')).lower() or "user"

            ticket_channel_name = f'{ticket_number}-{self.ticket_type.replace("_", "-")}-{user_name_safe}'[:100]

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True, manage_messages=True, read_message_history=True)
            }
            for role in roles_to_grant_perms:
                 overwrites[role] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, manage_messages=True, manage_channels=True, read_message_history=True, attach_files=True, embed_links=True)

            print(f"INFO: Tworzenie kanału '{ticket_channel_name}' w '{category.name}'...")
            ticket_channel = await category.create_text_channel(name=ticket_channel_name, overwrites=overwrites, reason=f"Ticket '{self.ticket_type}' by {user.display_name}")
            print(f"INFO: Utworzono kanał {ticket_channel.id} dla {user.display_name}")

            welcome_message_content = f"Witaj {user.mention}! Twój ticket typu **{self.ticket_type.replace('_', ' ').upper()}** został utworzony. Numer: **{ticket_number}**"
            if mention_string: welcome_message_content += f"\n\nPowiadomiono: {mention_string}"

            action_view = TicketActionView()
            welcome_msg = await ticket_channel.send(welcome_message_content, view=action_view)

            config.setdefault('ticket_creators', {})[str(ticket_channel.id)] = {
                'user_id': user.id, 'type': self.ticket_type, 'welcome_msg_id': welcome_msg.id if welcome_msg else None
            }
            save_config()
            print(f"INFO: Zapisano dane dla kanału {ticket_channel.id} (Twórca: {user.id}, Typ: {self.ticket_type}, MsgID: {welcome_msg.id if welcome_msg else 'Brak'})")

            user_info_embed = discord.Embed(title="Informacje o użytkowniku", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            user_info_embed.set_author(name=f"{user.display_name}", icon_url=user.display_avatar.url)
            user_info_embed.add_field(name="Użytkownik", value=f"{user.mention} (`{user.id}`)", inline=False)
            member_roles = [r.mention for r in sorted(user.roles[1:], key=lambda r: r.position, reverse=True)]
            roles_text = "\n".join(member_roles) if member_roles else "Brak"
            if len(roles_text) > 1024: roles_text = roles_text[:1020] + "\n..."
            user_info_embed.add_field(name=f"Role ({len(member_roles)})", value=roles_text, inline=False)
            try: await ticket_channel.send(embed=user_info_embed)
            except discord.Forbidden: print(f"[OSTRZEŻENIE] Brak uprawnień 'Embed Links' w kanale {ticket_channel.id}")
            except Exception as e_embed: print(f"[BŁĄD] Wysyłanie embed info w {ticket_channel.id}: {e_embed}")

            await interaction.followup.send(f"Utworzono ticket: {ticket_channel.mention}.", ephemeral=True)

        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as e:
            error_msg = f"Błąd tworzenia ticketa ({type(e).__name__})"; log_msg = error_msg
            if isinstance(e, discord.Forbidden): error_msg = f"Bot nie ma uprawnień: {e.text}"; log_msg = f"Forbidden: {error_msg} (Kat: {category_id})"
            elif isinstance(e, discord.HTTPException): error_msg = f"Błąd Discord API ({e.status})"; log_msg = f"HTTP {e.status}: {error_msg} (Kat: {category_id})"
            elif isinstance(e, discord.NotFound): error_msg = f"Nie znaleziono zasobu (kategorii {category_id}?)"; log_msg = f"NotFound: {error_msg}"
            print(f"[BŁĄD] Create Ticket Callback: {log_msg}")
            traceback.print_exc()
            if not interaction.is_expired(): await interaction.followup.send(f"{error_msg}. Sprawdź logi.", ephemeral=True)

            channel_exists = False
            if ticket_channel: channel_exists = guild.get_channel(ticket_channel.id) is not None
            if ticket_number > 0 and not channel_exists:
                 counters = config.setdefault('ticket_counters', {});
                 if self.ticket_type in counters and counters[self.ticket_type] >= ticket_number: counters[self.ticket_type] -= 1;
                 if counters[self.ticket_type] < 0: counters[self.ticket_type] = 0; save_config(); print(f"INFO: Wycofano licznik {self.ticket_type} z powodu błędu (nowy: {counters[self.ticket_type]}).")

        except Exception as e:
            print(f"[BŁĄD KRYTYCZNY] ConfirmButton.callback: {e}"); traceback.print_exc()
            if not interaction.is_expired(): await interaction.followup.send("Nieoczekiwany błąd serwera.", ephemeral=True)
            channel_exists_critical = False
            if ticket_channel: channel_exists_critical = guild.get_channel(ticket_channel.id) is not None
            if ticket_number > 0 and not channel_exists_critical:
                 counters = config.setdefault('ticket_counters', {});
                 if self.ticket_type in counters and counters[self.ticket_type] >= ticket_number: counters[self.ticket_type] -= 1;
                 if counters[self.ticket_type] < 0: counters[self.ticket_type] = 0; save_config(); print(f"INFO: Wycofano licznik {self.ticket_type} z powodu błędu kryt. (nowy: {counters[self.ticket_type]}).")


class TicketButton(Button):
    def __init__(self, ticket_type: str, *args, **kwargs):
        if not isinstance(ticket_type, str): raise TypeError("ticket_type must be a string")
        super().__init__(*args, **kwargs, custom_id=f"create_ticket_{ticket_type}")
        self.ticket_type = ticket_type

    async def callback(self, interaction: discord.Interaction):
        global config
        user = interaction.user
        guild = interaction.guild
        ticket_creators = config.get('ticket_creators', {})
        closed_cat_id_str = config.get('ticket_categories', {}).get('zamkniete', '-1')
        closed_cat_id = int(closed_cat_id_str) if closed_cat_id_str.isdigit() else -1
        active_ticket_channel_id = None

        for channel_id_str, creator_data in ticket_creators.items():
             if isinstance(creator_data, dict) and creator_data.get('user_id') == user.id and creator_data.get('type') == self.ticket_type:
                try:
                    channel = guild.get_channel(int(channel_id_str))
                    if channel and isinstance(channel, discord.TextChannel) and channel.category_id != closed_cat_id:
                        active_ticket_channel_id = channel_id_str; break
                except (ValueError, TypeError, AttributeError): continue

        if active_ticket_channel_id:
            await interaction.response.send_message(f"Masz już aktywny ticket typu **'{self.ticket_type.replace('_', ' ').upper()}'**: <#{active_ticket_channel_id}>.", ephemeral=True)
            return

        timestamp = int(discord.utils.utcnow().timestamp())
        confirm_custom_id = f"confirm_{self.ticket_type}_{user.id}_{timestamp}"
        cancel_custom_id = f"cancel_{self.ticket_type}_{user.id}_{timestamp}"

        confirm_view = View(timeout=120)

        confirm_button = ConfirmButton(ticket_type=self.ticket_type, label="Potwierdź", style=discord.ButtonStyle.green, custom_id=confirm_custom_id)
        cancel_button = Button(label="Anuluj", style=discord.ButtonStyle.red, custom_id=cancel_custom_id)

        async def cancel_callback(cancel_interaction: discord.Interaction):
            try: expected_user_id = int(cancel_interaction.data['custom_id'].split('_')[-2])
            except (IndexError, ValueError, KeyError): expected_user_id = None
            if expected_user_id != cancel_interaction.user.id:
                 await cancel_interaction.response.send_message("To nie jest Twoje zapytanie.", ephemeral=True); return

            await cancel_interaction.response.edit_message(content="Anulowano tworzenie ticketa.", view=None)
            confirm_view.stop()

        cancel_button.callback = cancel_callback

        confirm_view.add_item(confirm_button); confirm_view.add_item(cancel_button)

        async def on_timeout():
             try: await interaction.edit_original_response(content="Czas na potwierdzenie utworzenia ticketa minął.", view=None)
             except discord.NotFound: pass
             except Exception as e: print(f"BŁĄD: Edycja wiad. TicketButton po timeout: {e}")
        confirm_view.on_timeout = on_timeout

        await interaction.response.send_message(f"Czy na pewno chcesz utworzyć ticket typu **{self.ticket_type.replace('_', ' ').upper()}**?", view=confirm_view, ephemeral=True)


async def disable_ticket_buttons(channel: discord.TextChannel):
    global config
    channel_id_str = str(channel.id)
    creator_data = config.get('ticket_creators', {}).get(channel_id_str)
    welcome_msg_id = creator_data.get('welcome_msg_id') if isinstance(creator_data, dict) else None

    if not welcome_msg_id:
        print(f"[INFO] disable_ticket_buttons: Brak ID wiadomości powitalnej dla {channel_id_str}, pomijanie.")
        return

    try:
        welcome_msg = await channel.fetch_message(welcome_msg_id)
        if welcome_msg and welcome_msg.components:
            disabled_view = TicketActionView()
            for item in disabled_view.children:
                item.disabled = True
            await welcome_msg.edit(content=welcome_msg.content.split("\n\n**(Ticket Zamknięty)**")[0] + "\n\n**(Ticket Zamknięty)**", view=disabled_view)
            print(f"INFO: Zaktualizowano widok wiad. powitalnej {welcome_msg_id} w kanale {channel_id_str} na nieaktywny.")
        elif welcome_msg:
            print(f"INFO: Wiad. powitalna {welcome_msg_id} nie ma komponentów do wyłączenia.")
    except discord.NotFound:
        print(f"[OSTRZEŻENIE] disable_ticket_buttons: Nie znaleziono wiad. powitalnej {welcome_msg_id}.")
    except discord.Forbidden:
        print(f"[BŁĄD] disable_ticket_buttons: Brak uprawnień do edycji wiad. {welcome_msg_id} w {channel_id_str}.")
    except Exception as e:
        print(f"[BŁĄD] disable_ticket_buttons: Nieoczekiwany błąd przy aktualizacji widoku {welcome_msg_id}: {e}")
        traceback.print_exc()

async def _internal_close_ticket(channel: discord.TextChannel, guild: discord.Guild, closing_user: discord.Member, reason: str = None) -> tuple[bool, str]:
    global config
    channel_id_str = str(channel.id)
    print(f"--- Rozpoczynanie _internal_close_ticket dla kanału {channel_id_str} przez {closing_user.display_name} ---")

    ticket_creators = config.get('ticket_creators', {})
    creator_data = ticket_creators.get(channel_id_str)

    if not creator_data or not isinstance(creator_data, dict) or 'user_id' not in creator_data:
        msg = "Błąd: Kanał nie znaleziony w aktywnych ticketach (brak danych twórcy w configu)."
        print(f"[BŁĄD] _internal_close_ticket [{channel_id_str}]: {msg}")
        return False, msg

    creator_user_id = creator_data.get('user_id')
    ticket_type = creator_data.get('type', 'unknown')
    current_category_id = channel.category_id

    if not ticket_type or ticket_type == 'unknown':
        print(f"[OSTRZEŻENIE] _internal_close_ticket [{channel_id_str}]: Typ 'unknown'. Próba odgadnięcia z kategorii...")
        if current_category_id:
            category_id_to_key = {str(v): k for k, v in config.get('ticket_categories', {}).items() if isinstance(v, str) and v.isdigit() and k != 'zamkniete'}
            guessed_ticket_type = category_id_to_key.get(str(current_category_id))
            if guessed_ticket_type:
                ticket_type = guessed_ticket_type
                print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Odgadnięty typ: {ticket_type}")
            else: print(f"[OSTRZEŻENIE] _internal_close_ticket [{channel_id_str}]: Nie udało się odgadnąć typu z kategorii ID: {current_category_id}. Pozostaje 'unknown'.")
        else: print(f"[OSTRZEŻENIE] _internal_close_ticket [{channel_id_str}]: Kanał nie ma kategorii, nie można odgadnąć typu.")

    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
    if not closed_category_id:
        msg = "Błąd krytyczny configu: Kategoria 'Zamknięte' nie jest poprawnie zdefiniowana (brak lub złe ID)."
        print(f"[BŁĄD] _internal_close_ticket [{channel_id_str}]: {msg}")
        return False, msg

    if current_category_id == closed_category_id:
         print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Kanał już jest w kategorii 'zamkniete'. Kontynuacja (np. dla pewności ustawienia perms/nazwy).")

    allowed_role_names = config.get('ticket_role_mapping', {}).get(ticket_type, []) if ticket_type != 'unknown' else []
    all_roles_config = config.get('ticket_roles', {})
    allowed_role_ids = []
    for role_name in allowed_role_names:
        role_id_str = all_roles_config.get(role_name)
        if role_id_str and role_id_str.isdigit(): allowed_role_ids.append(int(role_id_str))
        else: print(f"[OSTRZEŻENIE] _internal_close_ticket [{channel_id_str}]: Nieprawidłowe/brak ID dla roli staffu '{role_name}' (typ: {ticket_type}).")
    allowed_roles = [guild.get_role(role_id) for role_id in allowed_role_ids if guild.get_role(role_id)]

    closed_category = guild.get_channel(closed_category_id)
    if not closed_category:
         try: closed_category = await guild.fetch_channel(closed_category_id)
         except (discord.NotFound, discord.Forbidden) as e:
              msg = f"Błąd pobierania kategorii 'Zamknięte' (ID: {closed_category_id}): {e}"
              print(f"[BŁĄD] _internal_close_ticket [{channel_id_str}]: {msg}")
              return False, msg
         except Exception as e:
              print(f"[BŁĄD] _internal_close_ticket fetch closed category: {e}"); return False, "Błąd serwera przy pobieraniu kat. 'Zamknięte'."
    if not isinstance(closed_category, discord.CategoryChannel):
         msg = f"Błąd configu: ID ({closed_category_id}) dla 'Zamknięte' nie jest kategorią."
         print(f"[BŁĄD] _internal_close_ticket [{channel_id_str}]: {msg}"); return False, msg

    permission_status = "Nie zmieniono"; move_status = "Nie przeniesiono"; rename_status = "Nie zmieniono"
    config_update_status = "Nie dotyczy"; final_channel_message_status = "Nie wysłano"

    try:
        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Ustawianie nadpisań (Typ: {ticket_type})...")
        staff_overwrite = discord.PermissionOverwrite(view_channel=True, read_messages=True, read_message_history=True, send_messages=True, add_reactions=True, attach_files=True, embed_links=True, manage_messages=True, manage_channels=True)
        creator_overwrite = discord.PermissionOverwrite()
        everyone_overwrite = discord.PermissionOverwrite(view_channel=False)
        new_overwrites = { guild.default_role: everyone_overwrite, guild.me: staff_overwrite }
        role_names_added = []
        for role in allowed_roles: new_overwrites[role] = staff_overwrite; role_names_added.append(role.name)
        ticket_creator_member = guild.get_member(creator_user_id)
        creator_status = "Nie znaleziono"
        if ticket_creator_member: new_overwrites[ticket_creator_member] = creator_overwrite; creator_status = f"'{ticket_creator_member.display_name}' (Usunięto)"
        else: print(f"[OSTRZEŻENIE] _internal_close_ticket [{channel_id_str}]: Nie znaleziono twórcy ID: {creator_user_id}")

        await channel.edit(overwrites=new_overwrites, reason=f"Ticket zamknięty przez {closing_user.display_name}")
        permission_status = f"Twórca: {creator_status}, Role: {', '.join(role_names_added) or 'Brak'}"
        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Zastosowano nadpisania.")

        if channel.category_id != closed_category.id:
            print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Przenoszenie do '{closed_category.name}'...")
            await channel.move(category=closed_category, end=True, sync_permissions=False, reason=f"Ticket zamknięty przez {closing_user.display_name}")
            move_status = f"Przeniesiono do '{closed_category.name}'"
            print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Przeniesiono.")
        else: move_status = "Już w kat. 'Zamknięte'"

        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Zmiana nazwy...")
        original_name = channel.name
        clean_original_name = original_name[len("closed-"):] if original_name.startswith("closed-") else original_name
        new_name = f"closed-{clean_original_name}"[:100]
        if channel.name != new_name:
            await channel.edit(name=new_name, reason=f"Ticket zamknięty przez {closing_user.display_name}")
            rename_status = f"Zmieniono na '{new_name}'"
            print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Zmieniono nazwę.")
        else: rename_status = "Bez zmian (poprawna)"

        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Aktualizacja configu...")
        removed_creator_data = config.get('ticket_creators', {}).pop(channel_id_str, None)
        removed_request_data = config.get('closure_requests', {}).pop(channel_id_str, None)
        if removed_creator_data or removed_request_data:
            try: save_config(); config_update_status = f"Usunięto dane: Twórca={'Tak' if removed_creator_data else 'Nie'}, Prośba={'Tak' if removed_request_data else 'Nie'}"
            except Exception as e_save: config_update_status = f"Błąd zapisu configu: {e_save}"
        else: config_update_status = "Nic do usunięcia"
        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Config: {config_update_status}")

        print(f"[INFO] _internal_close_ticket [{channel_id_str}]: Finalizowanie...")
        final_message = f"**Ticket został zamknięty** przez {closing_user.mention}."
        if reason: final_message += f"\n**Powód:** {reason}"
        try:
             await channel.send(final_message); final_channel_message_status = "Wysłano"
             await disable_ticket_buttons(channel)
        except Exception as e_final: final_channel_message_status = f"Błąd ({type(e_final).__name__})"; print(f"BŁĄD _internal_close final msg/disable: {e_final}")

        summary = (
            f"Zamykanie <#{channel.id}> (typ: {ticket_type}) zakończone pomyślnie.\n"
            f"— Uprawnienia: {permission_status}\n"
            f"— Przeniesienie: {move_status}\n"
            f"— Nazwa: {rename_status}\n"
            f"— Config: {config_update_status}\n"
            f"— Wiadomość: {final_channel_message_status}"
        )
        print(f"--- Zakończono _internal_close_ticket dla {channel_id_str}: Sukces ---")
        return True, summary

    except discord.Forbidden as e:
        print(f"[BŁĄD] _internal_close_ticket (Forbidden) [{channel_id_str}]: {e.text} (Status: {e.status}, Code: {e.code})")
        error_summary = f"Błąd uprawnień bota przy zamykaniu <#{channel.id}>: {e.text}\n(Krok Uprawnień: {permission_status}, Przeniesienia: {move_status}, Nazwy: {rename_status})"
        return False, error_summary
    except discord.HTTPException as e:
        print(f"[BŁĄD] _internal_close_ticket (HTTP) [{channel_id_str}]: {e.status} - {e.text}")
        error_summary = f"Błąd komunikacji Discord ({e.status}) przy zamykaniu <#{channel.id}>.\n(Krok Uprawnień: {permission_status}, Przeniesienia: {move_status}, Nazwy: {rename_status})"
        return False, error_summary
    except Exception as e:
        print(f"[KRYTYCZNY BŁĄD] _internal_close_ticket [{channel_id_str}]: {type(e).__name__}: {e}")
        traceback.print_exc()
        error_summary = f"Nieoczekiwany błąd przy zamykaniu <#{channel.id}>: {type(e).__name__}.\n(Krok Uprawnień: {permission_status}, Przeniesienia: {move_status}, Nazwy: {rename_status})"
        return False, error_summary


async def create_ticket_panel_view():
    view = View(timeout=None)
    types = ["aiad", "skarga", "high_command", "urlop", "odwolanie", "inne", "swat"]
    label_map = {"aiad": "AIAD", "skarga": "SKARGA", "high_command": "HIGH COMMAND", "urlop": "URLOP", "odwolanie": "ODWOŁANIE", "inne": "INNE", "swat": "SWAT"}
    button_styles = {
        "aiad": discord.ButtonStyle.danger, "skarga": discord.ButtonStyle.danger,
        "high_command": discord.ButtonStyle.secondary, "urlop": discord.ButtonStyle.success,
        "odwolanie": discord.ButtonStyle.secondary, "inne": discord.ButtonStyle.primary,
        "swat": discord.ButtonStyle.secondary
    }
    for type_key in types:
        label = label_map.get(type_key, type_key.replace("_", " ").upper())
        style = button_styles.get(type_key, discord.ButtonStyle.primary)
        button = TicketButton(ticket_type=type_key, label=label, style=style)
        view.add_item(button)
    return view

async def send_or_update_ticket_panel(guild_id: int, channel_id: int):
    global config
    guild = bot.get_guild(guild_id)
    if not guild: print(f"BŁĄD: send_or_update_ticket_panel: Nie znaleziono serwera {guild_id}."); return
    channel = None
    try:
        channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden) as e:
        print(f"BŁĄD: send_or_update_ticket_panel: Nie można pobrać kanału {channel_id}: {e}"); return
    except Exception as e: print(f"BŁĄD: send_or_update_ticket_panel: Pobieranie kanału {channel_id}: {e}"); return
    if not isinstance(channel, discord.TextChannel):
        print(f"BŁĄD: send_or_update_ticket_panel: ID {channel_id} nie jest kanałem tekstowym."); return

    view = await create_ticket_panel_view()
    panel_content = "**SYSTEM ZGŁOSZEŃ**\n\nWybierz odpowiednią kategorię, aby utworzyć zgłoszenie:"
    message_id = None
    if config.get('ticket_panel_message_id') and str(config['ticket_panel_message_id']).isdigit():
        message_id = int(config['ticket_panel_message_id'])

    try:
        panel_message = None
        if message_id:
            try:
                panel_message = await channel.fetch_message(message_id)
                await panel_message.edit(content=panel_content, view=view)
                print(f"INFO: Zaktualizowano panel ticketów (Wiadomość: {panel_message.id}) na kanale {channel.name}.")
            except discord.NotFound: message_id = None; config['ticket_panel_message_id'] = None; save_config(); print(f"INFO: Stara wiad. panelu ({message_id}) nie znaleziona. Wysyłanie nowej.")
            except discord.Forbidden: print(f"BŁĄD: Brak uprawnień do edycji wiad. panelu ({message_id}) w {channel.name}."); return
            except Exception as e_edit: message_id = None; config['ticket_panel_message_id'] = None; save_config(); print(f"BŁĄD: Edycja wiad. panelu ({message_id}): {e_edit}"); traceback.print_exc()

        if not message_id and panel_message is None:
            print(f"INFO: Wysyłanie nowego panelu na kanał {channel.name}...")
            if not channel.permissions_for(guild.me).send_messages: print(f"BŁĄD: Brak uprawnień 'Send Messages' w {channel.name}."); return
            if not channel.permissions_for(guild.me).embed_links: print(f"OSTRZEŻENIE: Brak uprawnień 'Embed Links' w {channel.name}.")
            new_message = await channel.send(content=panel_content, view=view)
            config['ticket_panel_message_id'] = str(new_message.id)
            save_config()
            print(f"INFO: Wysłano nowy panel (Wiadomość: {new_message.id}).")
    except discord.Forbidden: print(f"BŁĄD: Brak uprawnień do operacji na kanale {channel.name} (np. fetch/send).")
    except Exception as e: print(f"BŁĄD KRYTYCZNY: send_or_update_ticket_panel: {e}"); traceback.print_exc()


async def send_ticket_panel_if_configured():
    channel_id_str = config.get('ticket_panel_channel_id')
    if channel_id_str and str(channel_id_str).isdigit():
        try:
            channel_id_int = int(channel_id_str)
            print(f"INFO: Znaleziono config kanału panelu ({channel_id_int}). Wysyłanie/aktualizacja...")
            await send_or_update_ticket_panel(GUILD_ID, channel_id_int)
        except (ValueError, TypeError): print(f"BŁĄD: ID kanału panelu ('{channel_id_str}') nie jest liczbą.")
        except Exception as e: print(f"BŁĄD: send_ticket_panel_if_configured: {e}"); traceback.print_exc()
    else: print("INFO: ID kanału panelu ticketów nie jest skonfigurowane.")

async def handle_admin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    response_method = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    if isinstance(error, app_commands.MissingPermissions):
        missing_perms = ', '.join(error.missing_permissions)
        await response_method(f"Brak wymaganych uprawnień Discord: `{missing_perms}`.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await response_method("Nie spełniasz warunków użycia tej komendy (brak uprawnień?).", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
          original = error.original
          print(f"BŁĄD (CommandInvokeError): Komenda admina '{interaction.command.name if interaction.command else 'N/A'}': {original}")
          traceback.print_exception(type(original), original, original.__traceback__)
          if isinstance(original, discord.Forbidden): await response_method(f"Błąd uprawnień bota Discord: {original.text}", ephemeral=True)
          else: await response_method(f"Wewnętrzny błąd komendy: {type(original).__name__}. Sprawdź logi.", ephemeral=True)
    else:
        print(f"BŁĄD (Inny AppCommand): Komenda admina '{interaction.command.name if interaction.command else 'N/A'}': {error}")
        traceback.print_exc()
        await response_method(f"Nieoczekiwany błąd przetwarzania: {type(error).__name__}", ephemeral=True)


@bot.tree.command(name="close_ticket", description="Zamknij ten ticket (ustawia permisje, przenosi, zmienia nazwę).", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(powod="Opcjonalny powód zamknięcia ticketa")
async def close_ticket_command(interaction: discord.Interaction, powod: str = None):
    channel = interaction.channel
    user = interaction.user
    print(f"\n--- Otrzymano /close: Kanał ID: {channel.id}, przez: {user.name} ({user.id}) ---")

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True); return

    creator_data = config.get('ticket_creators', {}).get(str(channel.id))
    if not creator_data or not isinstance(creator_data, dict):
        await interaction.response.send_message("Wygląda na to, że nie jest to aktywny kanał ticketa zarządzany przez bota.", ephemeral=True); return

    creator_id = creator_data.get('user_id')
    is_creator = (creator_id == user.id) if creator_id else False
    has_manage_channels_perm = channel.permissions_for(user).manage_channels
    if not has_manage_channels_perm and not is_creator:
        await interaction.response.send_message("Nie masz uprawnień do zamknięcia tego ticketa.", ephemeral=True); return

    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
    if closed_category_id and channel.category_id == closed_category_id:
         print(f"INFO: /close [{channel.id}] użyte na już zamkniętym kanale.")

    view = ConfirmationView(original_interaction=interaction, powod=powod)
    print(f"[INFO] /close [{channel.id}]: Wysyłanie prośby o potwierdzenie do {user.name}...")
    await interaction.response.send_message(f"{user.mention}, czy na pewno chcesz zamknąć ten ticket (<#{channel.id}>)?", view=view, ephemeral=True)
    view.message = await interaction.original_response()
    print(f"[INFO] /close [{channel.id}]: Wysłano prośbę o potwierdzenie.")


@bot.tree.command(name="send_ticket_panel", description="Ustawia kanał dla panelu ticketów i wysyła/aktualizuje panel.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(kanał="Kanał tekstowy, na którym ma się pojawić panel ticketów")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_ticket_panel(interaction: discord.Interaction, kanał: discord.TextChannel):
    await interaction.response.defer(ephemeral=True, thinking=True)
    global config
    config['ticket_panel_channel_id'] = str(kanał.id)
    config['ticket_panel_message_id'] = None
    save_config()
    print(f"INFO: Ustawiono kanał panelu na {kanał.id} ({kanał.name}) przez {interaction.user.display_name}")
    await interaction.followup.send(f"Ustawiono kanał panelu na {kanał.mention}. Rozpoczynam wysyłanie/aktualizację panelu...", ephemeral=True)
    await send_ticket_panel_if_configured()

@setup_ticket_panel.error
async def setup_ticket_panel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="show_config", description="Pokazuje aktualną konfigurację ticketów (tylko dla adminów).", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    global config; load_config()
    try: config_str = json.dumps(config, indent=4, ensure_ascii=False, sort_keys=True)
    except Exception as e: await interaction.followup.send(f"Błąd formatowania configu: {e}", ephemeral=True); return

    limit = 1980
    if len(config_str) <= limit: await interaction.followup.send(f"```json\n{config_str}\n```", ephemeral=True)
    else:
        parts = []; current_part = ""
        for line in config_str.splitlines(True):
             if len(current_part) + len(line) > limit: parts.append(current_part); current_part = line
             else: current_part += line
        if current_part: parts.append(current_part)
        first = True
        for i, part in enumerate(parts):
             content_to_send = f"```json\n{part}\n```"
             try:
                 send_method = interaction.followup.send if not first else interaction.followup.send
                 await send_method(content_to_send, ephemeral=True)
                 first = False
             except discord.HTTPException as e_followup: print(f"Błąd wysyłania części {i+1} configu: {e_followup}"); break

@show_config.error
async def show_config_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="set_category", description="Ustaw ID kategorii dla danego typu ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(typ_ticketu=[
        app_commands.Choice(name="AIAD", value="aiad"),
        app_commands.Choice(name="Skarga", value="skarga"),
        app_commands.Choice(name="High Command", value="high_command"),
        app_commands.Choice(name="Urlop", value="urlop"),
        app_commands.Choice(name="Odwołanie", value="odwolanie"),
        app_commands.Choice(name="Inne", value="inne"),
        app_commands.Choice(name="SWAT", value="swat"),
        app_commands.Choice(name="Zamknięte", value="zamkniete")
])

@app_commands.describe(id_kategorii="Wprowadź numeryczne ID kategorii z Discorda")
async def set_ticket_category(interaction: discord.Interaction, typ_ticketu: str, id_kategorii: str):
    global config
    if not id_kategorii.isdigit(): await interaction.response.send_message("ID kategorii musi być liczbą.", ephemeral=True); return
    category_id_int = int(id_kategorii)
    try:
        category = interaction.guild.get_channel(category_id_int) or await interaction.guild.fetch_channel(category_id_int)
        if not category: raise discord.NotFound
        if not isinstance(category, discord.CategoryChannel): await interaction.response.send_message(f"Kanał ID {category_id_int} ('{category.name}') nie jest kategorią.", ephemeral=True); return
    except (discord.NotFound, discord.Forbidden) as e: await interaction.response.send_message(f"Nie można znaleźć/zweryfikować kategorii ID {category_id_int}: {e}", ephemeral=True); return
    except Exception as e: print(f"Błąd weryfikacji kategorii {category_id_int}: {e}"); await interaction.response.send_message("Błąd weryfikacji ID.", ephemeral=True); return

    config.setdefault('ticket_categories', {})[typ_ticketu] = id_kategorii
    save_config()
    await interaction.response.send_message(f"ID kategorii dla typu **'{typ_ticketu}'** ustawiono na **{id_kategorii}** (`{category.name}`).", ephemeral=True)

@set_ticket_category.error
async def set_ticket_category_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="set_role", description="Ustaw ID roli Discord dla nazwy roli.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.choices(nazwa_roli=[
    app_commands.Choice(name="AIAD", value="aiad"),
    app_commands.Choice(name="High Command", value="high_command"),
    app_commands.Choice(name="Command Staff", value="command_staff")
])
@app_commands.describe(nazwa_roli="Wewnętrzna nazwa roli (np. 'Aiad', 'Command Staff')", id_roli="ID roli z Discorda")
async def set_ticket_role(interaction: discord.Interaction, nazwa_roli: str, id_roli: str):
    global config
    if not id_roli.isdigit(): await interaction.response.send_message("ID roli musi być liczbą.", ephemeral=True); return
    role_id_int = int(id_roli)
    role_obj = interaction.guild.get_role(role_id_int)
    if not role_obj:
        try: await interaction.guild.fetch_roles(); role_obj = interaction.guild.get_role(role_id_int)
        except discord.Forbidden: await interaction.response.send_message("Bot nie ma uprawnień do pobrania ról.", ephemeral=True); return
        except Exception as e: print(f"Błąd fetch roles: {e}"); await interaction.response.send_message("Błąd weryfikacji ID roli.", ephemeral=True); return
        if not role_obj: await interaction.response.send_message(f"Nie znaleziono roli o ID {role_id_int}.", ephemeral=True); return

    config.setdefault('ticket_roles', {})[nazwa_roli] = id_roli
    save_config()
    await interaction.response.send_message(f"ID roli dla nazwy **'{nazwa_roli}'** ustawiono na **{id_roli}** ({role_obj.mention}).", ephemeral=True)

@set_ticket_role.error
async def set_ticket_role_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="delete_ticket", description="Trwale usuwa zamknięty kanał ticketa (wymaga potwierdzenia).", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_channels=True)
async def delete_ticket(interaction: discord.Interaction):
    channel_to_delete = interaction.channel
    user = interaction.user
    channel_id_str = str(channel_to_delete.id)
    print(f"\n--- Otrzymano /delete_ticket: Kanał ID: {channel_id_str}, przez: {user.display_name} ---")

    if not isinstance(channel_to_delete, discord.TextChannel): await interaction.response.send_message("To nie jest kanał tekstowy.", ephemeral=True); return

    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
    if not closed_category_id: await interaction.response.send_message("Kategoria 'Zamknięte' nie jest skonfigurowana.", ephemeral=True); return
    if not channel_to_delete.category or channel_to_delete.category.id != closed_category_id:
        await interaction.response.send_message(f"Można usuwać tylko kanały w kategorii 'Zamknięte'.", ephemeral=True); return

    confirm_view = View(timeout=60.0); delete_msg = None
    async def confirm_delete(confirm_interaction: discord.Interaction):
        nonlocal delete_msg
        if confirm_interaction.user.id != interaction.user.id: await confirm_interaction.response.send_message("Tylko inicjator może potwierdzić.", ephemeral=True); return
        try:
            await confirm_interaction.response.defer(ephemeral=True)
            if delete_msg: await delete_msg.edit(content="Potwierdzono. Usuwanie kanału...", view=None)
            channel_name = channel_to_delete.name; reason = f"Kanał usunięty przez {user.display_name} ({user.id})"
            await channel_to_delete.delete(reason=reason)
            print(f"[INFO] /delete_ticket: Kanał '{channel_name}' ({channel_id_str}) usunięty.")
            await confirm_interaction.followup.send(f"Kanał `#{channel_name}` usunięty.", ephemeral=True)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e: print(f"BŁĄD /delete_ticket ({type(e).__name__}): {e}"); await confirm_interaction.followup.send(f"Błąd podczas usuwania: {e}", ephemeral=True)
        except Exception as e: print(f"BŁĄD KRYTYCZNY /delete_ticket: {e}"); traceback.print_exc(); await confirm_interaction.followup.send("Błąd krytyczny.", ephemeral=True)
        finally: confirm_view.stop()
    async def cancel_delete(cancel_interaction: discord.Interaction):
        if cancel_interaction.user.id != interaction.user.id: await cancel_interaction.response.send_message("Tylko inicjator może anulować.", ephemeral=True); return
        if delete_msg: await delete_msg.edit(content="Anulowano usuwanie.", view=None)
        confirm_view.stop()

    confirm_btn = Button(label="Tak, usuń", style=discord.ButtonStyle.danger, custom_id="confirm_del_tkt"); confirm_btn.callback = confirm_delete
    cancel_btn = Button(label="Nie, anuluj", style=discord.ButtonStyle.secondary, custom_id="cancel_del_tkt"); cancel_btn.callback = cancel_delete
    confirm_view.add_item(confirm_btn); confirm_view.add_item(cancel_btn)

    await interaction.response.send_message(f"**OSTRZEŻENIE:** Czy na pewno **trwale usunąć** kanał `{channel_to_delete.name}`? Akcja nieodwracalna.", view=confirm_view, ephemeral=True)
    delete_msg = await interaction.original_response()

@delete_ticket.error
async def delete_ticket_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="add_to_ticket", description="Dodaje użytkownika do tego kanału ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(użytkownik="Użytkownik do dodania")
@app_commands.checks.has_permissions(manage_channels=True)
async def add_user_to_ticket(interaction: discord.Interaction, użytkownik: discord.Member):
    channel = interaction.channel; invoker = interaction.user; channel_id_str = str(channel.id)
    print(f"\n--- /add_user: Kanał {channel_id_str}, User: {użytkownik.id}, By: {invoker.id} ---")
    if not isinstance(channel, discord.TextChannel): await interaction.response.send_message("Tylko na kanale tekstowym.", ephemeral=True); return
    if str(channel.id) not in config.get('ticket_creators', {}): await interaction.response.send_message("To nie jest aktywny kanał ticketa.", ephemeral=True); return
    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
    if closed_category_id and channel.category_id == closed_category_id: await interaction.response.send_message("Nie można dodawać do zamkniętego ticketa.", ephemeral=True); return

    await interaction.response.defer(ephemeral=True)
    overwrite = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True, add_reactions=True)
    try:
        await channel.set_permissions(użytkownik, overwrite=overwrite, reason=f"Dodany przez {invoker.display_name}")
        await interaction.followup.send(f"Dodano {użytkownik.mention}.", ephemeral=True)
        try: await channel.send(f"{użytkownik.mention} dodany przez {invoker.mention}.")
        except discord.Forbidden: print(f"[WARN] /add_user [{channel_id_str}]: No perms to send msg")
    except (discord.Forbidden, discord.HTTPException) as e: print(f"BŁĄD /add_user perm: {e}"); await interaction.followup.send(f"Błąd ustawiania uprawnień: {e}", ephemeral=True)
    except Exception as e: print(f"BŁĄD KRYT /add_user: {e}"); traceback.print_exc(); await interaction.followup.send("Błąd krytyczny.", ephemeral=True)

@add_user_to_ticket.error
async def add_user_to_ticket_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)


@bot.tree.command(name="delete_from_ticket", description="Usuwa użytkownika z tego kanału ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(użytkownik="Użytkownik, którego chcesz usunąć z ticketa")
@app_commands.checks.has_permissions(manage_channels=True)
async def remove_user_from_ticket(interaction: discord.Interaction, użytkownik: discord.Member):
    channel = interaction.channel
    invoker = interaction.user
    channel_id_str = str(channel.id)

    print(f"\n--- Rozpoczęto /remove_user: Kanał ID: {channel_id_str}, Użytkownik: {użytkownik.display_name} ({użytkownik.id}), przez: {invoker.display_name} ({invoker.id}) ---")

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True)
        return

    if użytkownik.id == bot.user.id:
        print(f"[INFO] /remove_user [{channel_id_str}]: Próba usunięcia bota ({bot.user.name}).")
        await interaction.response.send_message("Nie możesz usunąć bota z kanału ticketa za pomocą tej komendy.", ephemeral=True)
        return

    ticket_creators = config.get('ticket_creators', {})
    creator_data = ticket_creators.get(str(channel.id))
    if not creator_data:
        await interaction.response.send_message("Wygląda na to, że nie jest to aktywny kanał ticketa.", ephemeral=True)
        return

    creator_id = creator_data.get('user_id') if isinstance(creator_data, dict) else None
    if creator_id == użytkownik.id:
        await interaction.response.send_message("Nie możesz usunąć twórcy ticketa za pomocą tej komendy. Użyj komendy `/close`.", ephemeral=True)
        return

    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    closed_category_id = int(closed_category_id_str) if closed_category_id_str and closed_category_id_str.isdigit() else None
    if closed_category_id and channel.category_id == closed_category_id:
        print(f"[INFO] /remove_user [{channel_id_str}]: Usuwanie użytkownika z zamkniętego ticketa.")

    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        if użytkownik in channel.overwrites:
            await channel.set_permissions(użytkownik, overwrite=None, reason=f"Usunięty z ticketa przez {invoker.display_name} ({invoker.id})")
            print(f"[INFO] /remove_user [{channel_id_str}]: Usunięto nadpisania dla {użytkownik.display_name}.")
            await interaction.followup.send(f"Pomyślnie usunięto {użytkownik.mention} z tego ticketa.", ephemeral=True)
            try: await channel.send(f"{użytkownik.mention} został usunięty z tego ticketa przez {invoker.mention}.")
            except discord.Forbidden: print(f"[OSTRZEŻENIE] /remove_user [{channel_id_str}]: Brak uprawnień do wysłania wiadomości na kanale.")
        else:
             print(f"[INFO] /remove_user [{channel_id_str}]: Użytkownik {użytkownik.display_name} nie miał specyficznych nadpisań.")
             await interaction.followup.send(f"{użytkownik.mention} nie miał specyficznych uprawnień na tym kanale do usunięcia.", ephemeral=True)

    except discord.Forbidden:
        print(f"[BŁĄD] /remove_user [{channel_id_str}]: Bot nie ma uprawnień 'Manage Permissions'.")
        await interaction.followup.send("Bot nie ma uprawnień do zarządzania uprawnieniami na tym kanale.", ephemeral=True)
    except discord.HTTPException as e_perm:
        print(f"[BŁĄD] /remove_user [{channel_id_str}]: Błąd HTTP ({e_perm.status}) podczas set_permissions (usuwanie): {e_perm.text}")
        await interaction.followup.send("Wystąpił błąd komunikacji z Discord podczas usuwania uprawnień.", ephemeral=True)
    except Exception as e_perm_other:
        print(f"[BŁĄD KRYTYCZNY] /remove_user [{channel_id_str}]: {e_perm_other}")
        traceback.print_exc()
        await interaction.followup.send("Wystąpił nieoczekiwany błąd podczas usuwania uprawnień.", ephemeral=True)

    print(f"--- Zakończono /remove_user: Kanał ID: {channel_id_str} ---")

@remove_user_from_ticket.error
async def remove_user_from_ticket_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await handle_admin_command_error(interaction, error)

@bot.event
async def on_ready():
    print("-" * 30)
    print(f'Zalogowano jako: {bot.user.name} ({bot.user.id})')
    print(f'Połączono z {len(bot.guilds)} serwerami.')
    target_guild = bot.get_guild(GUILD_ID)
    if target_guild: print(f'Docelowy serwer: {target_guild.name} ({GUILD_ID})')
    else: print(f'!!! OSTRZEŻENIE: Nie znaleziono docelowego serwera ({GUILD_ID}) w cache bota! Komendy mogą nie działać poprawnie. !!!')
    print("-" * 30)

    print("INFO: Ładowanie configu...")
    load_config()

    print("INFO: Rejestrowanie trwałych widoków...")
    try:
        bot.add_view(TicketActionView())
        print("INFO: Zarejestrowano trwały widok TicketActionView.")
    except Exception as e:
        print(f"BŁĄD KRYTYCZNY podczas rejestracji trwałych widoków: {e}")
        traceback.print_exc()

    if GUILD_ID:
        target_guild_obj = discord.Object(id=GUILD_ID)
        print(f"INFO: Rozpoczynanie synchronizacji komend aplikacji dla serwera {GUILD_ID}...")
        try:
            synced_commands = await bot.tree.sync(guild=target_guild_obj)

            print(f"INFO: Pomyślnie zsynchronizowano {len(synced_commands)} komend dla serwera {GUILD_ID}.")

            if synced_commands:
                print("INFO: Lista zsynchronizowanych komend:")
                for cmd in sorted(synced_commands, key=lambda c: c.name):
                    print(f"  -> /{cmd.name} (ID: {cmd.id})")
            else:
                print("INFO: Brak komend do zsynchronizowania lub lista jest pusta.")

        except discord.Forbidden as e_sync:
            print(f"BŁĄD KRYTYCZNY (Forbidden) podczas synchronizacji komend: Bot nie ma uprawnień 'application.commands' na serwerze {GUILD_ID} lub autoryzacja OAuth2 była bez tego scope.")
            print(f"   Szczegóły błędu: {e_sync}")
        except discord.HTTPException as e_sync_http:
             print(f"BŁĄD KRYTYCZNY (HTTPException) podczas synchronizacji komend: {e_sync_http.status} - {e_sync_http.text}")
        except Exception as e_sync:
            print(f"BŁĄD KRYTYCZNY podczas synchronizacji komend aplikacji: {e_sync}")
            traceback.print_exc()
    else:
        print("OSTRZEŻENIE: GUILD_ID nie jest ustawione! Komendy nie zostaną zsynchronizowane.")

    print("INFO: Sprawdzanie/aktualizacja panelu ticketów...")
    await send_ticket_panel_if_configured()

    print("-" * 30 + f"\n>>> Bot {bot.user.name} GOTOWY! <<<\n" + "-" * 30)


if __name__ == '__main__':
    print("INFO: Rozpoczynanie procesu uruchamiania bota...")
    token_valid = isinstance(TOKEN, str) and len(TOKEN) > 55
    guild_id_valid = isinstance(GUILD_ID, int) and GUILD_ID != PLACEHOLDER_GUILD_ID
    if not token_valid: print("="*40 + "\n BŁĄD KRYTYCZNY: Token bota jest nieprawidłowy lub nieustawiony! \n" + "="*40)
    elif not guild_id_valid: print("="*40 + f"\n BŁĄD KRYTYCZNY: GUILD_ID ({GUILD_ID}) jest nieprawidłowe! \n" + "="*40)
    else:
        try: bot.run(TOKEN, log_handler=None)
        except discord.LoginFailure: print("="*40 + "\n BŁĄD KRYTYCZNY: Nieprawidłowy token. \n" + "="*40)
        except discord.PrivilegedIntentsRequired as e: missing = str(e).split("'")[1]; print("="*40 + f"\n BŁĄD KRYTYCZNY: Brak intencji '{missing}'! Włącz ją na Discord Dev Portal i w kodzie. \n" + "="*40)
        except TypeError as e:
            if 'intents' in str(e).lower(): print("="*40 + f"\n BŁĄD KRYTYCZNY: Problem z intencjami: {e} \n" + "="*40)
            else: print("="*40 + f"\n BŁĄD KRYTYCZNY (TypeError): {e} \n" + "="*40); traceback.print_exc()
        except Exception as e: print("="*40 + f"\n BŁĄD KRYTYCZNY startu: {type(e).__name__} - {e} \n" + "="*40); traceback.print_exc()
