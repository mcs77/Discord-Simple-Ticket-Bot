# Simple Discord Ticket Bot
###
## Functions:
#### - Binding categories for tickets like: Administration, Moderators, Supports, Closed
#### - Addind users to ticket
#### - Deleting users from ticket
#### - Sending panel to channel
#### - Easy to add new tickets
#### - Deleting tickets
#### - Closing tickets
#### - Config in JSON
#### - Sending embed with user information after creating ticket
#### - Confirmation of closing, deleting + asking owner of ticket for closing
##
## Commands:
#### /get_role - panel to get roles by emoji (react to get)
#### /close_ticket - closing ticket
#### /set_ticket_panel - sending panel to channel
#### /show_config - showing config
#### /set_category - for binding categories using ids
#### /set_role - set roles, then use in mapping
#### /delete_from_ticket - deleting user from ticket
#### /add_to_ticket - adding user to ticket
##
## Every INFO + Debug + Errors are in polish, needs translation
## Bot was created for POLISH FiveM LSPD
##
##
## Examples of commands
#### /add_to_ticket mcs77
#### /delete_from_ticket mcs77
#### /set_category aiad 1111(id) (easy to add new ones, showing below)
#### /set_role aiad 1111(id) (easy to add new ones, showing below)
#### /set_ticket_panel (choose from list of channels)
#### /get_role (choose from list of channels)
###
###
###
###
# Configuring new categories and roles
## For example categories:
### Part of code:
#### @app_commands.choices(typ_ticketu=[
####        app_commands.Choice(name="AIAD", value="aiad"),
####        app_commands.Choice(name="Skarga", value="skarga"),
####        app_commands.Choice(name="High Command", value="high_command"),
####        app_commands.Choice(name="Urlop", value="urlop"),
####        app_commands.Choice(name="Odwołanie", value="odwolanie"),
####        app_commands.Choice(name="Inne", value="inne"),
####        app_commands.Choice(name="SWAT", value="swat"),
####        app_commands.Choice(name="Zamknięte", value="zamkniete")
#### ])
### If you want to add new one just follow sentance, for example
#### app_commands.Choice(name="New", value="github_example")
###
###
###
## Now roles:
### Some part of code:
#### @app_commands.choices(nazwa_roli=[
####    app_commands.Choice(name="AIAD", value="aiad"),
####    app_commands.Choice(name="High Command", value="high_command"),
####    app_commands.Choice(name="Command Staff", value="command_staff")
#### ])
### To add new one you just have to follow sentance:
#### app_commands.Choice(name="New_Role", value="Github_Role")
###
## If you will do everything correct, bot will just show your own new options (you also can edit mine ofc) in slash command
