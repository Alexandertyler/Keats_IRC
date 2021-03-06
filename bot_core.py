import socket
import time
import random
import sys
from os import listdir

import importlib

#importing tools for the subprocess launched to handle the irc client
from multiprocess import Process, Pipe
from multiprocess.connection import Listener, Client

#ignore_list = []
#
#
#def parse_commands(chan, nick, msg):
#    print chan, nick, msg
#
#    if chan == botnick:
#        chan = nick
#
#    if nick in ignore_list:
#        return
#
#    if msg == '.help':
#        print_help(nick)
#    
#    if msg.startswith(".ignore"):
#        if nick == 'alex':
#            user = msg.split('.ignore ')[1]
#            ignore(chan, user)
#
#    if msg.startswith(".poll"):
#        poll(chan, nick, msg)
#
#
#def ignore(chan, user):
#    if not user in ignore_list:
#        ignore_list.append(user)
#    ircsock.send("PRIVMSG " + chan + " :Due to high levels of spam in the vicinity, " + user + " will be ignored\n") 
#
#

def joinchannel(ircsock, chan):
    ircsock.send("JOIN  " + chan + "\n")
    
def verify(ircsock):
    waiting_to_verify = True
    while waiting_to_verify:
        ircmsg = ircsock.recv(2048)
        ircmsg.strip('\n\r')

        if ircmsg.find("PING :") != -1:
            response = ircmsg.split("PING ")[1]
            ircsock.send("PONG "+ response+"\n")
            waiting_to_verify = False


def login_routine(server, port, bot_nick, channel):
    #handle defaults for server, port, and nickname
    #default channel is to not join one
    if not server:
        server='127.0.0.1'
    if not port:
        port=6667
    if not bot_nick:
        bot_nick='keats'

    ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ircsock.connect((server, int(port)))
    ircsock.send("USER "+ bot_nick +" "+ bot_nick +" "+ bot_nick +" :Developed by Cyberdyne Systems\n")
    ircsock.send("NICK " + bot_nick +"\n")

    #need to figure out case for verify
    verify(ircsock)

    if channel:
        joinchannel(ircsock, channel)
    
    #have to do this after verification
    ircsock.setblocking(0)
    
    return ircsock, server, port, bot_nick, channel


def load_irc_commands(irc_dict, reload_commands=False):
    modules = [f for f in listdir('irc_commands') if f.startswith('irc')]
    for f_name in modules:
        module = f_name.split('.py')[0]
        command = module.split('irc_')[1]

        if reload_commands:
            if irc_dict.get(command):
                mod = getattr(__import__('irc_commands'), module)
                reload(mod)
            else:
                importlib.import_module('irc_commands.' + module)
        else:
            #import the module for the first time
            importlib.import_module('irc_commands.' + module)  
        #store the module into our shell commands dictionary
        irc_dict[command]=module

    return irc_dict


def load_shell_commands(shell_dict, reload_commands=False):
    modules = [f for f in listdir('shell_commands') if f.startswith('shell')]
    for f_name in modules:
        module = f_name.split('.py')[0]
        command = module.split('shell_')[1]

        if reload_commands:
            if shell_dict.get(command):
                mod = getattr(__import__('shell_commands'), module)
                reload(mod)
            else:
                importlib.import_module('shell_commands.' + module)
        else:
            #import the module for the first time
            importlib.import_module('shell_commands.' + module)  
        #store the module into our shell commands dictionary
        shell_dict[command]=module

    return shell_dict
    
#the main irc connection loop
#handles all irc communication
#communicates with main process via listener
def irc_loop(ircsock, bot_nick, channel, client):
    irc_dict = load_irc_commands({})
    
    while 1:
        #check for console commands
        if client.poll():
            shell_command = client.recv()
            shell_command = shell_command.split(':')
            
            if shell_command[0] == 'reload':
                irc_dict = load_irc_commands(irc_dict, reload_commands=True)
                continue 
            
            valid_shell = irc_dict.get(shell_command[0])
            if valid_shell:
                module = getattr(__import__('irc_commands'), valid_shell)
                try:
                    module.action(ircsock, channel, 'shell', shell_command[1])
                except IndexError:
                    module.action(ircsock, channel, 'shell', '')

        try:
            ircmsg = ircsock.recv(2048)
            ircmsg = ircmsg.strip('\n\r')

            if ircmsg.find("PING :") != -1:
                response = ircmsg.split("PING ")[1]
                ircsock.send("PONG "+ response+"\n")


            if ircmsg.find(' PRIVMSG ') != 1:
                chan = ircmsg.split(' PRIVMSG ')[-1].split(' :')[0]
                nick = ircmsg.split('!')[0][1:]
                msg = ircmsg.split(' PRIVMSG ')[-1].split(' :')[1]
        
                if msg.startswith('.'):
                    irc_command = msg.split(' ')[0]
                    irc_command = irc_command.split('.')[1]
                    valid_irc = irc_dict.get(irc_command)
                    if valid_irc:
                        module = getattr(__import__('irc_commands'),  valid_irc)
                        module.action(ircsock, channel, nick, msg)
            time.sleep(0.2)
        except:
            time.sleep(0.2)
            continue


#our main loop that the user interacts with
#has its own set of commands for controlling the bot or the script
def shell_loop(ircsock, channel, listener):
    connection = listener.accept()

    #using this method so I can reload it later if need be
    shell_dict = load_shell_commands({})

    while 1:
        command = raw_input('irc_bot: ')
        command = command.split(':')

        if command[0] == 'reload':
            connection.send('reload')
            shell_dict = load_shell_commands(shell_dict, reload_commands=True)
            continue
        
        valid = shell_dict.get(command[0])
        if valid:
            module = getattr(__import__('shell_commands'), valid)
            try:
                module.action(connection, command[1])
            except IndexError:
                module.action(connection, '')

        time.sleep(0.2)
        


if __name__ == "__main__":

    server = raw_input('Enter server: ')
    port = raw_input('Enter port: ')
    bot_nick = raw_input('Enter bot nick: ')
    channel = raw_input('Enter channel: ')

    ircsock, server, port, bot_nick, channel = login_routine(server, port, bot_nick, channel)
   
    #information for inter-process communication
    address = ('localhost', 2424)
    listener = Listener(address)
    client = Client(address)

    #two processes, one for console one for the irc channel
    irc = Process(target=irc_loop, args=(ircsock, bot_nick, channel, client))
    irc.start()

    #launch into the shell loop for interactive commands
    shell_loop(ircsock, channel, listener)
