import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
from discord import TextStyle
import json
import os
import traceback

TOKEN = 'TOKEN'

try:
    GUILD_ID = 1111111 # server id
except ValueError:
    print("BŁĄD: GUILD_ID musi być liczbą całkowitą!")
    exit()
except NameError:
     print("BŁĄD: Zmienna GUILD_ID nie została zdefiniowana!")
     exit()

if GUILD_ID == 123456789012345678:
    print("="*40)
    print(" BŁĄD KRYTYCZNY: ID serwera (GUILD_ID) jest ustawione na wartość domyślną! ")
    print(" Ustaw poprawne ID serwera w zmiennej GUILD_ID. ")
    print("="*40)
    exit()

intents = discord.Intents.default()
intents.members = True
intents.message_content = False

bot = commands.Bot(command_prefix=None, intents=intents)

CONFIG_FILE = 'ticket_config.json'
config = {
    'ticket_categories': {}, 'ticket_roles': {}, 'ticket_role_mapping': {},
    'ticket_panel_channel_id': None, 'ticket_panel_message_id': None,
    'ticket_counters': {}, 'ticket_creators': {}
}

def load_config():
    global config
    config = {
        'ticket_categories': {}, 'ticket_roles': {}, 'ticket_role_mapping': {},
        'ticket_panel_channel_id': None, 'ticket_panel_message_id': None,
        'ticket_counters': {}, 'ticket_creators': {}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                config['ticket_categories'] = loaded_config.get('ticket_categories', {})
                config['ticket_roles'] = loaded_config.get('ticket_roles', {})
                config['ticket_role_mapping'] = loaded_config.get('ticket_role_mapping', {})
                config['ticket_panel_channel_id'] = loaded_config.get('ticket_panel_channel_id')
                config['ticket_panel_message_id'] = loaded_config.get('ticket_panel_message_id')
                config['ticket_counters'] = loaded_config.get('ticket_counters', {})
                config['ticket_creators'] = loaded_config.get('ticket_creators', {})
                print(f"INFO: Config załadowany z {CONFIG_FILE}")
        except json.JSONDecodeError as e:
            print(f"BŁĄD: Błąd dekodowania JSON w {CONFIG_FILE}: {e}. Używam domyślnego configu.")
        except Exception as e:
            print(f"BŁĄD: Błąd podczas odczytu {CONFIG_FILE}: {e}. Używam domyślnego configu.")
    else:
        print(f"INFO: Plik {CONFIG_FILE} nie istnieje. Używam domyślnego configu.")

def save_config():
    global config
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"BŁĄD: Nie udało się zapisać configu do {CONFIG_FILE}: {e}")

@bot.tree.command(name="close", description="Zamknij ten ticket", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(powod="Opcjonalny powód zamknięcia ticketa")
async def close_ticket(interaction: discord.Interaction, powod: str = None):
    channel = interaction.channel
    guild = interaction.guild
    user = interaction.user
    channel_id_str = str(channel.id)

    print(f"\n--- Rozpoczęto /close: Kanał ID: {channel_id_str}, przez: {user.name} ({user.id}) ---")

    try:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Tej komendy można użyć tylko na kanale tekstowym ticketa.", ephemeral=True); return
        ticket_creators = config.get('ticket_creators', {})
        if channel_id_str not in ticket_creators:
            await interaction.followup.send("Wygląda na to, że nie jest to aktywny kanał ticketa zarządzany przez bota.", ephemeral=True); return

        creator_id_str = ticket_creators.get(channel_id_str)
        is_creator = False
        if creator_id_str:
            try: is_creator = (int(creator_id_str) == user.id)
            except ValueError: print(f"[OSTRZEŻENIE] /close [{channel_id_str}]: Złe ID twórcy w configu: {creator_id_str}")
        has_manage_channels_perm = channel.permissions_for(user).manage_channels
        if not is_creator and not has_manage_channels_perm:
            await interaction.followup.send("Nie jesteś twórcą tego ticketa ani nie masz uprawnień do zarządzania kanałami, aby go zamknąć.", ephemeral=True); return

        current_category_id = channel.category_id
        ticket_type_key = None

        if not current_category_id:
            print(f"[BŁĄD] /close [{channel_id_str}]: Kanał nie jest w żadnej kategorii.")
            await interaction.followup.send("Błąd: Ten kanał ticketa nie znajduje się w żadnej kategorii.", ephemeral=True); return

        category_id_to_key = {v: k for k, v in config.get('ticket_categories', {}).items()}
        ticket_type_key = category_id_to_key.get(str(current_category_id))

        if not ticket_type_key:
            print(f"[BŁĄD] /close [{channel_id_str}]: Kategoria kanału (ID: {current_category_id}) nie została znaleziona w configu 'ticket_categories'.")
            await interaction.followup.send(f"Błąd: Kategoria, w której znajduje się ten ticket (ID: {current_category_id}), nie jest rozpoznana w configu bota. Nie można ustalić typu ticketa.", ephemeral=True); return

        if ticket_type_key == 'zamkniete':
             print(f"[BŁĄD] /close [{channel_id_str}]: Kanał jest już w kategorii 'zamkniete' lub kategoria ma klucz 'zamkniete'.")
             await interaction.followup.send("Błąd: Ten kanał jest już (lub jego kategoria jest skonfigurowana jako) 'zamkniete'. Nie można ponownie zastosować logiki zamykania.", ephemeral=True); return

        closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
        allowed_role_names = config.get('ticket_role_mapping', {}).get(ticket_type_key, [])
        all_roles_config = config.get('ticket_roles', {})

        if not closed_category_id_str or not allowed_role_names:
             print(f"[BŁĄD] /close [{channel_id_str}]: Niekompletny config. Cat ID 'Zamknięte': {closed_category_id_str}, Role Names dla '{ticket_type_key}': {allowed_role_names}")
             await interaction.followup.send(f"Błąd configu: Brakuje definicji kategorii 'Zamknięte' lub ról dla typu ticketa '{ticket_type_key}'.", ephemeral=True); return

        allowed_role_ids = []
        for role_name in allowed_role_names:
            role_id_str = all_roles_config.get(role_name)
            if role_id_str:
                try: allowed_role_ids.append(int(role_id_str))
                except ValueError: print(f"[OSTRZEŻENIE] /close [{channel_id_str}]: Złe ID dla roli '{role_name}': {role_id_str}")
            else: print(f"[OSTRZEŻENIE] /close [{channel_id_str}]: Brak ID dla roli '{role_name}' w ticket_roles.")
        allowed_roles = [guild.get_role(role_id) for role_id in allowed_role_ids if guild.get_role(role_id) is not None]
        if not allowed_roles:
            await interaction.followup.send(f"Błąd configu: Nie znaleziono na serwerze żadnych ról zdefiniowanych dla typu ticketa '{ticket_type_key}'.", ephemeral=True); return

        closed_category = None
        try:
            closed_category_id = int(closed_category_id_str)
            closed_category = guild.get_channel(closed_category_id) or await guild.fetch_channel(closed_category_id)
            if not isinstance(closed_category, discord.CategoryChannel):
                await interaction.followup.send(f"Błąd configu: ID ({closed_category_id}) dla 'Zamknięte' nie jest kategorią.", ephemeral=True); return
        except ValueError: await interaction.followup.send("Błąd configu: Nieprawidłowe ID dla kategorii 'Zamknięte'.", ephemeral=True); return
        except (discord.NotFound, discord.Forbidden): await interaction.followup.send("Nie można znaleźć lub uzyskać dostępu do kategorii 'Zamknięte'.", ephemeral=True); return

        print(f"[INFO] /close [{channel_id_str}]: Przygotowywanie nadpisań uprawnień dla stanu zamkniętego (typ: {ticket_type_key})...")
        closed_overwrite_allowed = discord.PermissionOverwrite(view_channel=True, manage_channels=True, read_messages=True, read_message_history=True, send_messages=True, add_reactions=True, attach_files=True, embed_links=True)
        closed_overwrite_everyone = discord.PermissionOverwrite(view_channel=False)
        new_overwrites = { guild.default_role: closed_overwrite_everyone }
        for role in allowed_roles: new_overwrites[role] = closed_overwrite_allowed

        await channel.edit(overwrites=new_overwrites, reason=f"Ticket (typ: {ticket_type_key}) zamknięty przez {user.name} ({user.id})")
        print(f"[INFO] /close [{channel_id_str}]: Zastosowano nowe nadpisania uprawnień (tylko dla ról typu '{ticket_type_key}').")
        permission_status = f"Ustawiono ({', '.join(r.name for r in allowed_roles)})"

        move_status = "Pominięto (brak kategorii)"
        if closed_category:
             print(f"[INFO] /close [{channel_id_str}]: Próba przeniesienia kanału do kategorii '{closed_category.name}'...")
             try:
                 await channel.move(category=closed_category, end=True, sync_permissions=False, reason=f"Ticket zamknięty przez {user.name}")
                 move_status = "Sukces"
                 print(f"[INFO] /close [{channel_id_str}]: Kanał pomyślnie przeniesiony.")
             except discord.Forbidden as e_move: move_status = "Błąd Forbidden"; print(...)
             except discord.HTTPException as e_move_http: move_status = f"Błąd HTTP ({e_move_http.status})"; print(...)
             except Exception as e_move_other: move_status = "Inny Błąd"; print(...); traceback.print_exc()


        rename_status = "Pominięto"
        try:
            original_name = channel.name.replace('closed-', '')
            new_name = f"closed-{original_name}"[:100]
            if channel.name != new_name:
                await channel.edit(name=new_name, reason=f"Ticket zamknięty przez {user.name}")
                rename_status = f"Zmieniono na '{new_name}'"
                print(f"[INFO] /close [{channel_id_str}]: Zmieniono nazwę kanału na '{new_name}'.")
            else: rename_status = "Bez zmian"
        except discord.Forbidden: rename_status = "Błąd Forbidden"; print(...)
        except discord.HTTPException as e_rename: rename_status = f"Błąd HTTP ({e_rename.status})"; print(...)
        except Exception as e_rename_other: rename_status = "Inny Błąd"; print(...); traceback.print_exc()

        config_update_status = "Pominięto (brak wpisu)"
        ticket_creators_before_pop = config.get('ticket_creators', {})
        if channel_id_str in ticket_creators_before_pop:
             try:
                  removed_value = config['ticket_creators'].pop(channel_id_str, None)
                  if removed_value:
                       save_config()
                       config_update_status = "Usunięto wpis"
                       print(f"[INFO] /close [{channel_id_str}]: Usunięto wpis ticketa ({removed_value}) i zapisano config.")
                  else: config_update_status = "Klucz istniał, ale pop zwrócił None?"
             except KeyError: config_update_status = "Błąd KeyError (zniknął?)"; print(...)
             except Exception as e_save: config_update_status = f"Błąd zapisu ({type(e_save).__name__})"; print(...); traceback.print_exc()

        final_channel_message_status = "Nie wysłano"
        try:
            final_message = f"**Ticket został zamknięty** przez {user.mention}."
            if powod: final_message += f"\n**Powód:** {powod}"
            await channel.send(final_message)
            final_channel_message_status = "Wysłano"
        except Exception as e_send_final: final_channel_message_status = f"Błąd ({type(e_send_final).__name__})"; print(...)

        followup_summary = (
            f"Zamykanie <#{channel.id}> (typ: {ticket_type_key}) zakończone.\n" # Dodano typ
            f"- Uprawnienia: {permission_status}\n"
            f"- Przeniesienie: {move_status}\n"
            f"- Nazwa: {rename_status}\n"
            f"- Config: {config_update_status}\n"
            f"- Wiadomość na kanale: {final_channel_message_status}"
        )
        await interaction.followup.send(followup_summary, ephemeral=True)
        print(f"[INFO] /close [{channel_id_str}]: Podsumowanie followup wysłane.")

    except Exception as e:
        print(f"[KRYTYCZNY BŁĄD] /close [{channel_id_str}]: Nieoczekiwany błąd główny: {e}")
        traceback.print_exc()
        try:
            if not interaction.is_expired():
                 await interaction.followup.send("Wystąpił krytyczny błąd podczas zamykania ticketa. Sprawdź logi bota.", ephemeral=True)
        except Exception as e_followup:
            print(f"[KRYTYCZNY BŁĄD] /close [{channel_id_str}]: Nie udało się nawet wysłać wiadomości o błędzie: {e_followup}")

    print(f"--- Zakończono /close: Kanał ID: {channel_id_str} ---")

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
        closed_category_id = None

        if category_id_str and category_id_str.isdigit():
            category_id = int(category_id_str)
        else:
            await interaction.followup.send(f"ID kategorii dla typu '{self.ticket_type}' jest niepoprawne lub nieustawione w configu.", ephemeral=True)
            return

        if closed_category_id_str and closed_category_id_str.isdigit():
             closed_category_id = int(closed_category_id_str)

        if category_id == closed_category_id:
             await interaction.followup.send("Nie można tworzyć ticketów w kategorii 'Zamknięte'. Skonfiguruj inną kategorię dla tego typu.", ephemeral=True)
             return

        role_ids_to_mention = []
        roles_to_grant_perms = []
        role_mapping_for_type = config.get('ticket_role_mapping', {}).get(self.ticket_type, [])
        all_ticket_roles = config.get('ticket_roles', {})

        for role_name in role_mapping_for_type:
            role_id_str = all_ticket_roles.get(role_name)
            if role_id_str and role_id_str.isdigit():
                role_id = int(role_id_str)
                role = guild.get_role(role_id)
                if role:
                    role_ids_to_mention.append(str(role_id))
                    roles_to_grant_perms.append(role)
                else:
                    print(f"OSTRZEŻENIE: Nie znaleziono roli '{role_name}' o ID:{role_id} na serwerze.")
            elif role_id_str:
                 print(f"OSTRZEŻENIE: Nieprawidłowe ID dla roli '{role_name}' w configu: {role_id_str}")
            else:
                 print(f"OSTRZEŻENIE: Brak definicji ID dla roli '{role_name}' w 'ticket_roles', mimo że jest w mapowaniu dla '{self.ticket_type}'.")
        mention_string = ' '.join([f"<@&{role_id}>" for role_id in role_ids_to_mention]) if role_ids_to_mention else ""

        ticket_channel = None
        category = None
        ticket_number = 0
        try:
            category = guild.get_channel(category_id)
            if not category:
                 print(f"INFO: Kategoria '{self.ticket_type}' ({category_id}) brak w cache, próba pobrania...")
                 category = await guild.fetch_channel(category_id)

            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(f"Skonfigurowany ID ({category_id}) dla '{self.ticket_type}' nie jest kategorią.", ephemeral=True)
                return

            counters = config.setdefault('ticket_counters', {})
            counters[self.ticket_type] = counters.get(self.ticket_type, 0) + 1
            ticket_number = counters[self.ticket_type]
            save_config() # licznik

            safe_user_name = "".join(c for c in user.name if c.isalnum() or c in ('-', '_')).lower() or "user"
            ticket_channel_name = f'{self.ticket_type.replace("_", "-")}-{ticket_number}-{safe_user_name}'[:100]

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False), # @everyone nie widzi
                # tworca
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                ),
                # bot
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True,
                    manage_messages=True,
                    read_message_history=True
                )
            }
            # zmapowane
            for role in roles_to_grant_perms:
                 print(f"[INFO] Ticket Creation: Ustawianie uprawnień dla roli '{role.name}' (ID: {role.id})")
                 overwrites[role] = discord.PermissionOverwrite(
                     view_channel=True,             # widzenie kanału
                     read_messages=True,            # czytanie wiadomości
                     send_messages=True,            # pisanie wiadomości
                     manage_messages=True,          # zarzadzanie wiadomościami
                     manage_channels=True,          # zarzadzanie kanałem
                     read_message_history=True,     # czytanie historii
                     attach_files=True,             # zalaczanie plików
                     embed_links=True               # embedy
                 )
            # =========================================================

            print(f"INFO: Tworzenie kanału '{ticket_channel_name}' w kategorii '{category.name}' z nadpisaniami...")
            ticket_channel = await category.create_text_channel(
                name=ticket_channel_name,
                overwrites=overwrites,
                reason=f"Ticket '{self.ticket_type}' utworzony przez {user.name} ({user.id})"
            )
            print(f"INFO: Utworzono kanał: {ticket_channel.name} (ID: {ticket_channel.id}) dla {user.name}")

            config.setdefault('ticket_creators', {})[str(ticket_channel.id)] = user.id
            save_config()
            print(f"INFO: Zapisano twórcę {user.id} dla kanału {ticket_channel.id}")

            welcome_message = (
                 f"Witaj {user.mention}! Twój ticket typu **{self.ticket_type}** został utworzony.\n"
            )
            if mention_string:
                 welcome_message += f"\n\nPowiadomiono: {mention_string}"
            await ticket_channel.send(welcome_message)

            await interaction.followup.send(f"Utworzono ticket w kanale {ticket_channel.mention}.", ephemeral=True)

            try: await interaction.delete_original_response()
            except Exception as e: print(f"INFO: Nie można usunąć wiad. potwierdzenia: {e}")

        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as e:
            error_msg = "Błąd tworzenia ticketa.";
            if isinstance(e, discord.Forbidden): error_msg = "Bot nie ma uprawnień."; print(f"BŁĄD (Forbidden): {error_msg} Kat: {category_id}. E: {e}")
            elif isinstance(e, discord.HTTPException): error_msg = "Błąd komunikacji Discord."; print(f"BŁĄD (HTTP): {error_msg} Kat: {category_id}. E: {e}")
            elif isinstance(e, discord.NotFound): error_msg = f"Nie znaleziono kategorii ({category_id})."; print(f"BŁĄD (NotFound): {error_msg}")
            if not interaction.is_expired():
                 try: await interaction.followup.send(f"{error_msg}", ephemeral=True)
                 except Exception as e_f: print(f"BŁĄD: Wysyłanie followup błędu tworzenia: {e_f}")
            if ticket_number > 0 and (ticket_channel is None or not discord.utils.get(guild.text_channels, id=ticket_channel.id)):
                 counters = config.setdefault('ticket_counters', {});
                 if self.ticket_type in counters and counters[self.ticket_type] >= ticket_number: counters[self.ticket_type] -= 1;
                 if counters[self.ticket_type] < 0: counters[self.ticket_type] = 0; save_config(); print(f"INFO: Wycofano licznik {self.ticket_type} (nowy: {counters[self.ticket_type]}).")
        except Exception as e:
            print(f"BŁĄD KRYTYCZNY: ConfirmButton.callback: {e}"); traceback.print_exc()
            if not interaction.is_expired():
                 try: await interaction.followup.send("Nieoczekiwany błąd serwera.", ephemeral=True)
                 except Exception as e_f: print(f"BŁĄD: Wysyłanie followup błędu krytycznego: {e_f}")
            if ticket_number > 0 and (ticket_channel is None or not discord.utils.get(guild.text_channels, id=ticket_channel.id)):
                counters = config.setdefault('ticket_counters', {});
                if self.ticket_type in counters and counters[self.ticket_type] >= ticket_number: counters[self.ticket_type] -= 1;
                if counters[self.ticket_type] < 0: counters[self.ticket_type] = 0; save_config(); print(f"INFO: Wycofano licznik {self.ticket_type} (nowy: {counters[self.ticket_type]}).")

class TicketButton(Button):
    def __init__(self, ticket_type: str, *args, **kwargs):
        if not isinstance(ticket_type, str): raise TypeError("ticket_type must be a string")
        super().__init__(*args, **kwargs); self.ticket_type = ticket_type; self.custom_id = f"create_ticket_{self.ticket_type}"
    async def callback(self, interaction: discord.Interaction):
        global config; active_ticket_channel_id = None; user_id_to_check = interaction.user.id
        ticket_creators_dict = config.get('ticket_creators', {}); closed_cat_id_str = config.get('ticket_categories', {}).get('zamkniete', '-1')
        closed_cat_id = int(closed_cat_id_str) if closed_cat_id_str.isdigit() else -1
        for channel_id_str, creator_id in ticket_creators_dict.items():
            if creator_id == user_id_to_check:
                try: channel_id_int = int(channel_id_str); channel = interaction.guild.get_channel(channel_id_int)
                except (ValueError, TypeError): print(f"OSTRZEŻENIE: Nieprawidłowe ID kanału '{channel_id_str}' w creators."); continue
                if channel and isinstance(channel, discord.TextChannel):
                     expected_prefix = f'{self.ticket_type.replace("_", "-")}-';
                     if channel.name.startswith(expected_prefix) and channel.category_id != closed_cat_id: active_ticket_channel_id = channel_id_str; break
        if active_ticket_channel_id: await interaction.response.send_message(f"Masz już ticket **'{self.ticket_type}'** <#{active_ticket_channel_id}>.", ephemeral=True); return
        timestamp = int(discord.utils.utcnow().timestamp()); confirm_custom_id = f"confirm_{self.ticket_type}_{interaction.user.id}_{timestamp}"; cancel_custom_id = f"cancel_{self.ticket_type}_{interaction.user.id}_{timestamp}"
        confirm_view = View(timeout=120); confirm_button = ConfirmButton(ticket_type=self.ticket_type, label="Potwierdź", style=discord.ButtonStyle.green, custom_id=confirm_custom_id); cancel_button = Button(label="Anuluj", style=discord.ButtonStyle.red, custom_id=cancel_custom_id)
        async def cancel_callback(cancel_interaction: discord.Interaction):
            try: expected_user_id = int(cancel_interaction.data['custom_id'].split('_')[-2]);
            except (IndexError, ValueError): print(f"BŁĄD: Parsowanie Anuluj: {cancel_interaction.data['custom_id']}"); await cancel_interaction.response.send_message("Błąd wewn.", ephemeral=True); return
            if cancel_interaction.user.id != expected_user_id: await cancel_interaction.response.send_message("Nie twoje.", ephemeral=True); return
            await cancel_interaction.response.defer(ephemeral=True);
            try: await interaction.delete_original_response()
            except Exception: pass
        cancel_button.callback = cancel_callback; confirm_view.add_item(confirm_button); confirm_view.add_item(cancel_button)
        async def on_timeout():
             try: await interaction.edit_original_response(content="Czas minął.", view=None)
             except Exception: pass
        confirm_view.on_timeout = on_timeout
        await interaction.response.send_message(f"Utworzyć ticket **{self.ticket_type}**?", view=confirm_view, ephemeral=True)

async def create_ticket_panel_view():
    view = View(timeout=None)

    types = ["aiad", "skarga", "high_command", "urlop", "odwolanie"]

    label_map = {
        "aiad": "AIAD", "skarga": "Skarga", "high_command": "High Command",
        "urlop": "Urlop", "odwolanie": "Odwołanie"
    }
    button_styles = {
        "aiad": discord.ButtonStyle.primary,
        "skarga": discord.ButtonStyle.danger,
        "high_command": discord.ButtonStyle.secondary,
        "urlop": discord.ButtonStyle.success,
        "odwolanie": discord.ButtonStyle.secondary
    }

    for type_key in types:
        label = label_map.get(type_key, type_key.replace("_", " ").capitalize())
        style = button_styles.get(type_key, discord.ButtonStyle.primary)
        button = TicketButton(ticket_type=type_key, label=label, style=style)
        view.add_item(button)
    return view

async def send_or_update_ticket_panel(guild_id: int, channel_id: int):
    global config; guild = bot.get_guild(guild_id);
    if not guild: print(f"BŁĄD: Nie znaleziono serwera {guild_id}."); return; channel = None
    try: channel = await guild.fetch_channel(channel_id);
    except Exception as e: print(f"BŁĄD: Pobieranie kanału {channel_id}: {e}"); return
    if not isinstance(channel, discord.TextChannel): print(f"BŁĄD: ID {channel_id} nie jest kanałem tekstowym."); return
    view = await create_ticket_panel_view(); panel_content = "**TICKETY**\n\nWybierz kategorię:"; message_id = None;
    if config.get('ticket_panel_message_id'):
        try: message_id = int(config['ticket_panel_message_id'])
        except Exception: print(f"OSTRZEŻENIE: ID wiad. panelu w configu nie jest liczbą."); message_id = None
    try:
        if message_id:
            try: print(f"INFO: Fetch wiad. panelu {message_id}..."); panel_message = await channel.fetch_message(message_id); print(f"INFO: Edycja wiad. panelu {message_id}..."); await panel_message.edit(content=panel_content, view=view); print(f"INFO: Zaktualizowano panel (ID: {panel_message.id})");
            except discord.NotFound: print(f"INFO: Nie znaleziono wiad. {message_id}."); message_id = None; config['ticket_panel_message_id'] = None; save_config()
            except discord.Forbidden: print(f"BŁĄD: Bot nie ma praw edycji wiad. {message_id}."); return
            except Exception as e: print(f"BŁĄD: Edycja panelu ({message_id}): {e}"); message_id = None; config['ticket_panel_message_id'] = None; save_config(); traceback.print_exc()
        if not message_id:
            print(f"INFO: Wysyłanie nowego panelu na {channel.name}...");
            if not channel.permissions_for(guild.me).send_messages: print(f"BŁĄD: Bot nie ma praw 'Send Messages' na {channel.name}."); return
            if not channel.permissions_for(guild.me).embed_links: print(f"OSTRZEŻENIE: Bot nie ma praw 'Embed Links' na {channel.name}.")
            new_message = await channel.send(content=panel_content, view=view); config['ticket_panel_message_id'] = new_message.id; save_config(); print(f"INFO: Wysłano nowy panel (ID: {new_message.id})")
    except Exception as e: print(f"BŁĄD: send_or_update_ticket_panel: {e}"); traceback.print_exc()

async def send_ticket_panel_if_configured():
    channel_id_str = config.get('ticket_panel_channel_id')
    if channel_id_str:
        try: channel_id_int = int(channel_id_str); print(f"INFO: Config panelu OK (Kanał ID: {channel_id_int}). Wysyłanie..."); await send_or_update_ticket_panel(GUILD_ID, channel_id_int)
        except (ValueError, TypeError): print(f"BŁĄD: ID kanału panelu w configu ('{channel_id_str}') nie jest liczbą.")
        except Exception as e: print(f"BŁĄD: send_ticket_panel_if_configured: {e}"); traceback.print_exc()
    else: print("INFO: ID kanału panelu nie skonfigurowane.")

@bot.tree.command(name="set_ticket_panel", description="Ustawia kanał dla panelu ticketów.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(kanał="Kanał tekstowy dla panelu")
@app_commands.checks.has_permissions(manage_guild=True)
async def set_ticket_panel(interaction: discord.Interaction, kanał: discord.TextChannel):
    await interaction.response.defer(ephemeral=True); global config; config['ticket_panel_channel_id'] = kanał.id; config['ticket_panel_message_id'] = None; save_config()
    print(f"INFO: Ustawiono kanał panelu {kanał.id} przez {interaction.user.name}"); await interaction.followup.send(f"Ustawiono kanał panelu na {kanał.mention}. Wysyłam panel...", ephemeral=True); await send_ticket_panel_if_configured()

@bot.tree.command(name="show_config", description="Pokazuje config ticketów (admin).", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_guild=True)
async def show_config(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True); global config
    try: config_str = json.dumps(config, indent=4, ensure_ascii=False, sort_keys=True)
    except Exception as e: print(f"BŁĄD: Konwersja configu: {e}"); await interaction.followup.send("Błąd formatowania configu.", ephemeral=True); return
    limit = 1980
    if len(config_str) > limit:
        parts = []; current_part = "";
        for line in config_str.splitlines(True):
             if len(current_part) + len(line) > limit: parts.append(current_part); current_part = line
             else: current_part += line
        parts.append(current_part); first = True
        for part in parts: content = f"```json\n{part}\n```";
        if first: await interaction.followup.send(content, ephemeral=True); first = False
        else: await interaction.followup.send(content, ephemeral=True)
    else: await interaction.followup.send(f"```json\n{config_str}\n```", ephemeral=True)

@set_ticket_panel.error
async def set_ticket_panel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    response_method = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    if isinstance(error, app_commands.MissingPermissions): await response_method("Brak uprawnień `Manage Server`.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
          original = error.original; print(f"BŁĄD: Wykonanie /set_ticket_panel: {original}"); traceback.print_exception(type(original), original, original.__traceback__)
          if isinstance(original, discord.Forbidden): await response_method(f"Bot ma błąd uprawnień.", ephemeral=True)
          else: await response_method("Błąd wykonania komendy. Sprawdź logi.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): await response_method("Brak uprawnień.", ephemeral=True)
    else: print(f"BŁĄD: AppCommand /set_ticket_panel: {error}"); traceback.print_exc(); await response_method(f"Błąd przetwarzania: {error}", ephemeral=True)

@show_config.error
async def show_config_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    response_method = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
    if isinstance(error, app_commands.MissingPermissions): await response_method("No perms `Manage Server`.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): await response_method("No perms.", ephemeral=True)
    else: print(f"BŁĄD: /show_config: {error}"); traceback.print_exc(); await response_method("Błąd wykonania.", ephemeral=True)

@bot.tree.command(name="set_category", description="Ustaw ID kategorii dla danego typu ticketa", guild=discord.Object(id=GUILD_ID))
@app_commands.choices(typ_ticketu=[
    app_commands.Choice(name="AIAD", value="aiad"),
    app_commands.Choice(name="High Command", value="high_command"),
    app_commands.Choice(name="Urlop", value="urlop"),
    app_commands.Choice(name="Zamknięte", value="zamkniete"), # Ważne dla /close
    app_commands.Choice(name="Odwołanie", value="odwolanie"),
    app_commands.Choice(name="Skarga", value="skarga")
])
@app_commands.describe(id_kategorii="Wprowadź ID kategorii Discord")
async def set_category(interaction: discord.Interaction, typ_ticketu: str, id_kategorii: str):
    global config
    if not id_kategorii.isdigit():
         await interaction.response.send_message("Podane ID kategorii jest nieprawidłowe (musi być liczbą).", ephemeral=True)
         return

    try:
        category = interaction.guild.get_channel(int(id_kategorii))
        if not category or not isinstance(category, discord.CategoryChannel):
             try:
                  category = await interaction.guild.fetch_channel(int(id_kategorii))
                  if not isinstance(category, discord.CategoryChannel):
                       await interaction.response.send_message(f"ID {id_kategorii} nie jest kategorią.", ephemeral=True)
                       return
             except discord.NotFound:
                   await interaction.response.send_message(f"Nie znaleziono kategorii o ID {id_kategorii} na tym serwerze.", ephemeral=True)
                   return
             except discord.Forbidden:
                   await interaction.response.send_message(f"Bot nie ma uprawnień, by sprawdzić kategorię o ID {id_kategorii}.", ephemeral=True)
                   return
    except Exception as e:
         print(f"Błąd podczas sprawdzania kategorii {id_kategorii}: {e}")
         await interaction.response.send_message("Wystąpił błąd podczas sprawdzania ID kategorii.", ephemeral=True)
         return

    config['ticket_categories'][typ_ticketu] = id_kategorii
    save_config()
    await interaction.response.send_message(f"ID kategorii dla '{typ_ticketu}' zostało ustawione na: {id_kategorii} (<#{id_kategorii}>)", ephemeral=True)

@bot.tree.command(name="delete_ticket", description="Usuwa zamknięty kanał ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.checks.has_permissions(manage_channels=True)
async def delete_ticket(interaction: discord.Interaction):
    channel_to_delete = interaction.channel
    user = interaction.user
    channel_id_str = str(channel_to_delete.id)

    print(f"\n--- Rozpoczęto /delete_ticket: Kanał ID: {channel_id_str}, przez: {user.name} ({user.id}) ---")

    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
        print(f"[INFO] /delete_ticket [{channel_id_str}]: Interaction deferred.")
    except discord.NotFound:
         print(f"OSTRZEŻENIE: /delete_ticket [{channel_id_str}]: defer() - interakcja wygasła?")
         return
    except Exception as e_defer:
        print(f"[BŁĄD KRYTYCZNY] /delete_ticket [{channel_id_str}]: defer(): {e_defer}")
        return

    if not isinstance(channel_to_delete, discord.TextChannel):
        print(f"[INFO] /delete_ticket [{channel_id_str}]: Użyto na kanale nie-tekstowym.")
        await interaction.followup.send("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True)
        return

    closed_category_id = None
    closed_category_id_str = config.get('ticket_categories', {}).get("zamkniete")
    if closed_category_id_str and closed_category_id_str.isdigit():
        closed_category_id = int(closed_category_id_str)
    else:
        print(f"[BŁĄD] /delete_ticket [{channel_id_str}]: Nie skonfigurowano poprawnie kategorii 'Zamknięte'.")
        await interaction.followup.send("Kategoria 'Zamknięte' nie jest poprawnie skonfigurowana.", ephemeral=True)
        return

    print(f"[INFO] /delete_ticket [{channel_id_str}]: Sprawdzanie kategorii kanału (Oczekiwana: {closed_category_id})...")
    if not channel_to_delete.category or channel_to_delete.category.id != closed_category_id:
        current_cat_id = channel_to_delete.category.id if channel_to_delete.category else "Brak"
        print(f"[INFO] /delete_ticket [{channel_id_str}]: Kanał jest w kategorii {current_cat_id}, a nie {closed_category_id}.")
        await interaction.followup.send("Tej komendy można użyć tylko na kanale ticketa, który został już zamknięty.", ephemeral=True)
        return
    print(f"[INFO] /delete_ticket [{channel_id_str}]: Kanał jest w poprawnej kategorii 'Zamknięte'.")

    try:
        channel_name = channel_to_delete.name
        print(f"[INFO] /delete_ticket [{channel_id_str}]: Próba usunięcia kanału '{channel_name}'...")
        reason = f"Kanał ticketa usunięty przez {user.name} ({user.id})"
        await channel_to_delete.delete(reason=reason)
        print(f"[INFO] /delete_ticket: Kanał '{channel_name}' ({channel_id_str}) usunięty pomyślnie.")

        try:
             await interaction.followup.send(f"Kanał ticketa `#{channel_name}` został pomyślnie usunięty.", ephemeral=True)
        except discord.NotFound:
             print(f"[INFO] /delete_ticket [{channel_id_str}]: Nie można wysłać followup po usunięciu (interakcja wygasła?).")
        except Exception as e_followup_after_delete:
             print(f"[BŁĄD] /delete_ticket [{channel_id_str}]: Błąd wysyłania followup po usunięciu: {e_followup_after_delete}")

    except discord.Forbidden:
        print(f"[BŁĄD] /delete_ticket [{channel_id_str}]: Bot nie ma uprawnień do usunięcia kanału '{channel_to_delete.name}'.")
        await interaction.followup.send("Bot nie ma uprawnień 'Manage Channels' do usunięcia tego kanału.", ephemeral=True)
    except discord.NotFound:
        print(f"[INFO] /delete_ticket [{channel_id_str}]: Kanał '{channel_to_delete.name}' już nie istniał podczas próby usunięcia.")
        await interaction.followup.send("Wygląda na to, że ten kanał został już usunięty.", ephemeral=True)
    except discord.HTTPException as e:
        print(f"[BŁĄD] /delete_ticket [{channel_id_str}]: Błąd HTTP podczas usuwania kanału: {e}")
        await interaction.followup.send(f"Wystąpił błąd komunikacji z Discord ({e.status}). Spróbuj ponownie.", ephemeral=True)
    except Exception as e:
        print(f"[BŁĄD] /delete_ticket [{channel_id_str}]: Nieoczekiwany błąd podczas usuwania: {e}")
        traceback.print_exc()
        await interaction.followup.send("Wystąpił nieoczekiwany błąd serwera.", ephemeral=True)

    print(f"--- Zakończono /delete_ticket: Kanał ID: {channel_id_str} ---")

@bot.tree.command(name="set_roles", description="Ustaw ID roli dla grupy personelu", guild=discord.Object(id=GUILD_ID))
@app_commands.choices(rola=[
    app_commands.Choice(name="AIAD", value="aiad"),
    app_commands.Choice(name="High Command", value="high_command"),
    app_commands.Choice(name="Command Staff", value="command_staff"),
    # etc etc as here
])
@app_commands.describe(id_roli="Wprowadź ID roli Discord")
async def set_roles(interaction: discord.Interaction, rola: str, id_roli: str):
    global config
    if not id_roli.isdigit():
        await interaction.response.send_message("Podane ID roli jest nieprawidłowe (musi być liczbą).", ephemeral=True)
        return

    role_obj = interaction.guild.get_role(int(id_roli))
    if not role_obj:
         try:
              await interaction.guild.fetch_roles()
              role_obj = interaction.guild.get_role(int(id_roli))
              if not role_obj:
                    await interaction.response.send_message(f"Nie znaleziono roli o ID {id_roli} na tym serwerze.", ephemeral=True)
                    return
         except discord.Forbidden:
              await interaction.response.send_message("Bot nie ma uprawnień do pobrania listy ról.", ephemeral=True)
              return
         except Exception as e:
              print(f"Błąd podczas sprawdzania roli {id_roli}: {e}")
              await interaction.response.send_message("Wystąpił błąd podczas sprawdzania ID roli.", ephemeral=True)
              return


    config['ticket_roles'][rola] = id_roli
    save_config()
    await interaction.response.send_message(f"ID roli dla grupy '{rola}' zostało ustawione na: {id_roli} (<@&{id_roli}>)", ephemeral=True)

@bot.tree.command(name="add_ticket", description="Dodaje użytkownika do tego ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(użytkownik="Użytkownik, którego chcesz dodać")
@app_commands.checks.has_permissions(manage_channels=True)
async def dodaj_do_ticketa(interaction: discord.Interaction, użytkownik: discord.Member):
    channel = interaction.channel
    invoker = interaction.user
    channel_id_str = str(channel.id)

    print(f"\n--- Rozpoczęto /dodaj_ticket: Kanał ID: {channel_id_str}, Użytkownik do dodania: {użytkownik.display_name} ({użytkownik.id}), przez: {invoker.name} ({invoker.id}) ---")

    await interaction.response.defer(ephemeral=True, thinking=True)

    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True)
        return

    print(f"[INFO] /dodaj_ticket [{channel_id_str}]: Próba ustawienia uprawnień dla {użytkownik.display_name}...")
    overwrite = discord.PermissionOverwrite()
    overwrite.view_channel = True
    overwrite.send_messages = True
    overwrite.read_message_history = True
    overwrite.attach_files = True
    overwrite.embed_links = True

    try:
        await channel.set_permissions(użytkownik, overwrite=overwrite, reason=f"Dodany do ticketa przez {invoker.name} ({invoker.id})")
        print(f"[INFO] /dodaj_ticket [{channel_id_str}]: Ustawiono uprawnienia dla {użytkownik.display_name}.")
        await interaction.followup.send(f"Pomyślnie dodano {użytkownik.mention} do tego ticketa.", ephemeral=True)
        await channel.send(f"{użytkownik.mention} został dodany do tego ticketa przez {invoker.mention}.")
    except discord.Forbidden:
        print(f"[BŁĄD] /dodaj_ticket [{channel_id_str}]: Bot nie ma uprawnień 'Manage Permissions'/'Manage Roles' na kanale '{channel.name}'.")
        await interaction.followup.send("Bot nie ma uprawnień do zarządzania uprawnieniami na tym kanale.", ephemeral=True)
    except discord.HTTPException as e_perm:
        print(f"[BŁĄD] /dodaj_ticket [{channel_id_str}]: Błąd HTTP podczas set_permissions: {e_perm}")
        await interaction.followup.send("Wystąpił błąd komunikacji z Discord podczas ustawiania uprawnień.", ephemeral=True)
    except Exception as e_perm_other:
        print(f"[BŁĄD] /dodaj_ticket [{channel_id_str}]: Inny błąd set_permissions: {e_perm_other}")
        traceback.print_exc()
        await interaction.followup.send("Wystąpił nieoczekiwany błąd podczas ustawiania uprawnień.", ephemeral=True)

    print(f"--- Zakończono /dodaj_ticket: Kanał ID: {channel_id_str} ---")

@bot.tree.command(name="delete_from_ticket", description="Usuwa użytkownika z tego ticketa.", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(użytkownik="Użytkownik, którego chcesz usunąć")
@app_commands.checks.has_permissions(manage_channels=True)
async def delete_from_ticket(interaction: discord.Interaction, użytkownik: discord.Member): # użytkownik jest już obiektem discord.Member
    channel = interaction.channel
    invoker = interaction.user
    channel_id_str = str(channel.id)

    print(f"\n--- Rozpoczęto /usun_ticket: Kanał ID: {channel_id_str}, Użytkownik do usunięcia: {użytkownik.display_name} ({użytkownik.id}), przez: {invoker.name} ({invoker.id}) ---")

    await interaction.response.defer(ephemeral=True, thinking=True)

    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send("Tej komendy można użyć tylko na kanale tekstowym.", ephemeral=True)
        return

    ticket_creators = config.get('ticket_creators', {})
    if channel_id_str not in ticket_creators:
        await interaction.followup.send("Wygląda na to, że nie jest to aktywny kanał ticketa.", ephemeral=True)
    return

    creator_id_str = ticket_creators.get(channel_id_str)
    creator_id = None
    if creator_id_str:
        try:
            creator_id = int(creator_id_str)
        except ValueError:
            print(f"[OSTRZEŻENIE] /usun_ticket [{channel_id_str}]: Nieprawidłowe ID twórcy w configu: {creator_id_str}")

    if creator_id == użytkownik.id:
        print(f"[INFO] /usun_ticket [{channel_id_str}]: Próba usunięcia twórcy ticketa ({użytkownik.display_name}, ID: {użytkownik.id}). Operacja przerwana.")
        await interaction.followup.send("Nie możesz usunąć twórcy ticketa za pomocą tej komendy. Użyj komendy do zamykania ticketów.", ephemeral=True)
        return

    print(f"[INFO] /usun_ticket [{channel_id_str}]: Próba usunięcia nadpisań dla {użytkownik.display_name}...")
    try:
        if użytkownik in channel.overwrites:
            await channel.set_permissions(użytkownik, overwrite=None, reason=f"Usunięty z ticketa przez {invoker.name} ({invoker.id})")
            print(f"[INFO] /usun_ticket [{channel_id_str}]: Usunięto nadpisania dla {użytkownik.display_name}.")
            await interaction.followup.send(f"Pomyślnie usunięto {użytkownik.mention} z tego ticketa.", ephemeral=True)
            await channel.send(f"{użytkownik.mention} został usunięty z tego ticketa przez {invoker.mention}.")
        else:
             print(f"[INFO] /usun_ticket [{channel_id_str}]: Użytkownik {użytkownik.display_name} nie miał specyficznych nadpisań na tym kanale.")
             await interaction.followup.send(f"{użytkownik.mention} nie miał specyficznych uprawnień na tym kanale do usunięcia.", ephemeral=True)

    except discord.Forbidden:
        print(f"[BŁĄD] /usun_ticket [{channel_id_str}]: Bot nie ma uprawnień 'Manage Permissions'/'Manage Roles' na kanale '{channel.name}'.")
        await interaction.followup.send("Bot nie ma uprawnień do zarządzania uprawnieniami na tym kanale.", ephemeral=True)
    except discord.HTTPException as e_perm:
        print(f"[BŁĄD] /usun_ticket [{channel_id_str}]: Błąd HTTP podczas set_permissions (usuwanie): {e_perm}")
        await interaction.followup.send("Wystąpił błąd komunikacji z Discord podczas usuwania uprawnień.", ephemeral=True)
    except Exception as e_perm_other:
        print(f"[BŁĄD] /usun_ticket [{channel_id_str}]: Inny błąd set_permissions (usuwanie): {e_perm_other}")
        traceback.print_exc()
        await interaction.followup.send("Wystąpił nieoczekiwany błąd podczas usuwania uprawnień.", ephemeral=True)

    print(f"--- Zakończono /usun_ticket: Kanał ID: {channel_id_str} ---")

@bot.event
async def on_ready():
    print("-" * 30); print(f'Zalogowano: {bot.user.name} ({bot.user.id})'); print(f'discord.py: {discord.__version__}'); print("-" * 30); print("INFO: Ładowanie configu...")
    load_config(); default_keys = {'ticket_categories': {}, 'ticket_roles': {}, 'ticket_role_mapping': {}, 'ticket_panel_channel_id': None, 'ticket_panel_message_id': None, 'ticket_counters': {}, 'ticket_creators': {}}; needs_save = False
    for key, default in default_keys.items():
        if key not in config: config[key] = default; print(f"INFO: Dodano klucz '{key}'."); needs_save = True
    if needs_save: print("INFO: Zapisywanie configu..."); save_config()
    try: panel_view = await create_ticket_panel_view(); bot.add_view(panel_view); print("INFO: Zarejestrowano widok panelu.")
    except Exception as e: print(f"BŁĄD: Rejestracja widoku panelu: {e}"); traceback.print_exc()
    if GUILD_ID:
        print(f"INFO: Synchronizacja komend dla serwera {GUILD_ID}...");
        try: synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID)); print(f"INFO: Zsynchronizowano {len(synced)} komend.")
        except Exception as e: print(f"BŁĄD KRYTYCZNY (Sync): {e}"); traceback.print_exc()
    else: print("OSTRZEŻENIE: GUILD_ID nie ustawione, komendy nie zsynchronizowane.")
    print("INFO: Wysyłanie/aktualizacja panelu..."); await send_ticket_panel_if_configured(); print("-" * 30); print(f"Bot {bot.user.name} gotowy!"); print("-" * 30)

if __name__ == '__main__':
    print("INFO: Uruchamianie bota...")
    token_valid = TOKEN and TOKEN != 'TWOJ_TOKEN_BOTA'; guild_id_valid = isinstance(GUILD_ID, int) and GUILD_ID != 123456789012345678
    if not token_valid: print("="*40 + "\n BŁĄD: Token bota nie ustawiony! \n" + "="*40)
    elif not guild_id_valid: print("="*40 + f"\n BŁĄD: GUILD_ID ({GUILD_ID}) niepoprawne! \n" + "="*40)
    else:
        try: bot.run(TOKEN, log_handler=None)
        except discord.LoginFailure: print("="*40 + "\n BŁĄD: Nieprawidłowy token. \n" + "="*40)
        except discord.PrivilegedIntentsRequired as e: print("="*40 + f"\n BŁĄD: Brak intencji '{e.shard_id}'! \n Włącz w Discord Dev Portal.\n" + "="*40)
        except TypeError as e:
            if 'intents' in str(e).lower(): print("="*40 + "\n BŁĄD: Brak intencji (Members?). \n Sprawdź kod i Dev Portal.\n" + f" Error: {e}\n" + "="*40)
            else: print("="*40 + f"\n BŁĄD (TypeError): {e} \n" + "="*40); traceback.print_exc()
        except Exception as e: print("="*40 + f"\n BŁĄD uruchamiania: {e} \n" + "="*40); traceback.print_exc()
