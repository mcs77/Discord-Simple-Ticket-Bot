Simple Discord Ticket Bot 🎫

A versatile Discord bot designed for managing support tickets, initially created for a Polish FiveM LSPD community.
✨ Features

    Category Binding: Assign specific Discord categories for different ticket types (e.g., Administration, Moderators, Support, Closed).

    User Management: Easily add or remove users from specific tickets.

    Ticket Panel: Send an interactive button panel to a designated channel for easy ticket creation.

    Customizable Tickets: Simple process to add new ticket types.

    Ticket Lifecycle: Close and permanently delete tickets.

    Configuration: Manage bot settings through a ticket_config.json file.

    User Info Embed: Automatically sends an embed with user details upon ticket creation.

    Confirmations: Includes confirmation steps for closing/deleting tickets and a system for users to request ticket closure from the owner.

    Role Assignment: Panel for users to self-assign roles (Kadet/LSPD) via reactions.

🛠️ Commands

    /odbierz_role - Sends the panel for users to get roles via emoji reaction.

    /close - Closes the current ticket (moves to 'Closed' category, adjusts permissions, renames channel).

    /wyslij_panel - Sends or updates the ticket creation panel to the configured channel.

    /pokaz_config - Displays the current bot configuration (admin only).

    /ustaw_kategorie - Binds a Discord category ID to a specific ticket type (e.g., 'aiad', 'skarga', 'zamkniete').

    /ustaw_role - Sets the Discord role ID for a specific staff role name (used for permissions).

    /delete_ticket - Permanently deletes a closed ticket channel (requires confirmation).

    /dodaj_ticket - Adds a specified user to the current ticket channel.

    /usun_ticket - Removes a specified user from the current ticket channel.

⚙️ Configuration & Customization

The bot uses a ticket_config.json file for its settings. You can easily add new ticket types and roles directly in the Python code.
Adding New Ticket Categories

    Locate the @app_commands.choices decorator for the typ_ticketu argument within the /ustaw_kategorie command definition.

    Add a new app_commands.Choice line following the existing pattern.

@app_commands.choices(typ_ticketu=[
    app_commands.Choice(name="AIAD", value="aiad"),
    app_commands.Choice(name="Skarga", value="skarga"),
    # ... other choices ...
    app_commands.Choice(name="SWAT", value="swat"),
    app_commands.Choice(name="Zamknięte", value="zamkniete"),
    # Add your new category choice here:
    app_commands.Choice(name="New Example Category", value="new_example_category")
])

    Remember to also configure the ticket_role_mapping in your ticket_config.json if this new category requires specific staff roles.

    Use the /ustaw_kategorie command to link this new type (new_example_category) to a Discord category ID.

Adding New Staff Roles

    Locate the @app_commands.choices decorator for the nazwa_roli argument within the /ustaw_role command definition.

    Add a new app_commands.Choice line. The value should be a unique internal identifier for this staff group.

@app_commands.choices(nazwa_roli=[
    app_commands.Choice(name="AIAD", value="aiad_staff"), # Example: value = 'aiad_staff'
    app_commands.Choice(name="High Command", value="high_command"),
    app_commands.Choice(name="Command Staff", value="command_staff"),
    # Add your new role choice here:
    app_commands.Choice(name="New Staff Group", value="new_staff_group")
])

    Use the /ustaw_role command to link this internal name (new_staff_group) to a Discord role ID.

    Update the ticket_role_mapping in your ticket_config.json to assign this new staff group (new_staff_group) to the relevant ticket types.

🌍 Language Note

All internal logging messages (INFO, Debug, Errors) printed to the console are currently in Polish. The bot was initially developed for a Polish-speaking community. Translation might be needed for broader use.
