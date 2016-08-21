#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import os
import time
import json
import threading
import sublime
from re import compile, match
from shutil import move

from .Commands import CommandsPy
from . import Paths
from . import Tools
from .Messages import Console
from .Messages import MessageQueue
from .Preferences import Preferences
from .JSONFile import JSONFile
from .Menu import Menu
from .I18n import I18n
from .Progress import ThreadProgress
from . import __version__ as version
from .QuickPanel import quickPanel
from .configobj.configobj import ConfigObj

_ = I18n().translate


C = {
    'IOT': None,
    'FEEDBACK': None,
    'SKETCHPATH': None,
    'SKETCHDIR': None,
    'SKETCHSIZE': None,
    'FILENAME': None,
    'PARENTDIR': None,
    'NATIVE': None,
    'INIT': None,
    'INIPATH': None,
    'ENVIRONMENT': None,
    'WORKINGPATH': None,
    'TEMPNAME': None,
    'PORTSLIST': None,
    'PORT': None,
    'CALLBACK': None,
    'CMDS': None,
    'BUILT': None,
    'AUTH': None,
    'PORTINDEX': 0
}


class PlatformioCLI(CommandsPy):
    '''
    This class handle all the request to the platformio ecosystem.
    From the list of boards to the build/upload of the sketchs.
    More info about platformio in: http://platformio.org/

    Extends: CommandsPy
    '''

    def __init__(self, feedback=True):
        self.window = sublime.active_window()
        self.view = self.window.active_view()
        C['FEEDBACK'] = feedback

    def loadData(self):
        """
        Get and process data from the current file, if the file is
        being processing, shows errors or information in the user console
        """

        C['SKETCHPATH'] = Tools.getPathFromView(self.view)
        C['SKETCHSIZE'] = self.view.size()
        C['FILENAME'] = Tools.getNameFromPath(C['SKETCHPATH'])
        C['IOT'] = Tools.isIOTFile(C['SKETCHPATH'])
        C['PORT'] = Preferences().get('id_port', '')

        VIEWNAME = self.view.name().lower()
        CURRENTTIME = time.strftime('%H:%M:%S')

        # cancel feedback if quick panel will be used
        if(C['IOT']):
            if(not Tools.checkBoards() or
               not Tools.checkEnvironments() or
               not Preferences().get('id_port', False)):
                C['FEEDBACK'] = False

        # avoid to do anything with a monitor view
        if(C['FEEDBACK'] and not C['SKETCHPATH'] and 'monitor' in VIEWNAME):
            console = Console(self.window)
            self.message_queue = MessageQueue(console)
            self.message_queue.startPrint()
            self.message_queue.put('_deviot_{0}', version)
            self.message_queue.put('invalid_file_{0}', CURRENTTIME)
            return

        # Empty sketch
        if(C['FEEDBACK'] and not C['SKETCHSIZE']):
            console = Console(self.window)
            self.message_queue = MessageQueue(console)
            self.message_queue.startPrint()
            self.message_queue.put('_deviot_{0}', version)
            self.message_queue.put('not_empty_sketch_{0}', CURRENTTIME)
            C['BUILT'] = False
            return

        # stop if nothing to process and show
        if(not C['FEEDBACK'] and not C['IOT']):
            return

        # save file not empty
        if(not C['SKETCHPATH'] and C['SKETCHSIZE'] > 0):
            saved_file = self.saveCodeInFile(self.view)
            self.view = saved_file[1]
            C['SKETCHPATH'] = Tools.getPathFromView(self.view)
            C['FILENAME'] = Tools.getNameFromPath(C['SKETCHPATH'])
            TEMPNAME = Tools.getNameFromPath(C['SKETCHPATH'], ext=False)
            C['TEMPNAME'] = TEMPNAME
            C['IOT'] = Tools.isIOTFile(C['SKETCHPATH'])

        # check if file is iot
        if(C['FEEDBACK'] and not C['IOT']):
            console = Console(self.window)
            self.message_queue = MessageQueue(console)
            self.message_queue.startPrint()
            self.message_queue.put('_deviot_{0}', version)
            self.message_queue.put(
                'not_iot_{0}{1}', CURRENTTIME, C['FILENAME'])
            return

        # unsaved changes
        if (self.view.is_dirty()):
            self.view.run_command('save')

        C['NATIVE'] = Tools.isNativeProject(self.view)
        C['SKETCHPATH'] = Tools.getPathFromView(self.view)
        C['SKETCHDIR'] = Paths.getCWD(C['SKETCHPATH'])
        C['PARENTDIR'] = Paths.getParentPath(C['SKETCHPATH'])
        TEMPNAME = Tools.getNameFromPath(C['SKETCHPATH'], ext=False)
        C['TEMPNAME'] = TEMPNAME
        C['INIT'] = Tools.isIniFile(self.view)

        # Get the current environment
        TYPEPROJECT = Tools.getTypeEnvironment()
        C['ENVIRONMENT'] = Preferences().get(TYPEPROJECT, False)

        # set the current working path
        C['WORKINGPATH'] = Tools.getWorkingPath(self.view)
        INITPATH = os.path.join(C['WORKINGPATH'], 'platformio.ini')
        C['INIPATH'] = INITPATH

    def checkInitFile(self):
        """
        Check each platformio.ini file and loads the environments already
        initialized.
        """
        self.loadData()
        return

        # stop if platformio.ini not exist
        if(not C['INIT']):
            return

        protected = Preferences().get('protected', False)
        if(not protected):
            return

        # stop if it's not a IoT file
        if(not C['IOT']):
            return

        INIPATH = C['INIPATH']
        NATIVE = C['NATIVE']
        # only if platformio.ini exist
        if(not INIPATH):
            return

        # get data from platformio.ini file
        inilist = []
        INIFILE = ConfigObj(INIPATH)
        for environment in INIFILE:
            inilist.append(environment.split(":")[1])

        # save preferences, update menu data
        type = 'board_id' if not NATIVE else 'found_ini'

        if(NATIVE):
            current = Preferences().get(type, inilist)
            inilist.extend(current)
            inilist = list(set(inilist))
        Preferences().set(type, inilist)

    def beforeProcess(self, next):
        """
        Check if all the requirements are met based in the type of command. If
        it's necessary shows the quick panel to choose an option

        Arguments:
            next {str} -- name of the next method to call
        """
        self.loadData()

        PORT = C['PORT']

        if(not C['IOT']):
            return

        if(not C['CALLBACK']):
            C['CALLBACK'] = next

        # if none board is selected show a quick panel list
        if(not Tools.checkBoards()):
            choose = Menu().createBoardsMenu()
            quickPanel(choose, self.saveBoardCallback)
            return

        # if none environment is selected show a quick panel list
        if(not Tools.checkEnvironments()):
            list = Menu().getEnvironments()
            quickPanel(list[0], self.saveEnvironmetCallback, index=list[1])
            return

        if(next == 'upload' and not C['PORTSLIST']):
            self.openInThread(self.listSerialPorts, join=True)

        # check if the port is available
        if(next == 'upload'):
            if(not any(x[0] in PORT for x in C['PORTSLIST']) or PORT == ''):
                self.openInThread(self.selectPort)
                return

        mcu = self.getMCU()
        if(next == 'upload' and "esp" in mcu and "COM" not in PORT):
            # check if auth is required to mdns
            from . import Serial
            saved_auth = Preferences().get('auth', False)
            mdns = Serial.listMdnsServices()

            for service in mdns:
                try:
                    service = json.loads(service)
                    server = service['server']
                    if(server[:-1] == PORT):
                        auth = service["properties"]["auth_upload"]
                        C['AUTH'] = True if auth == 'yes' else False
                except:
                    pass

            # check if auth is required
            if(C['AUTH']):
                if(not saved_auth or saved_auth == '0' and self.mDNSCheck()):
                    self.window.show_input_panel(
                        _("pass_caption"), '', self.saveAuthPassword, None, None)
                return

        # Create and store the console
        try:
            C['CONSOLE'] = Console(self.window)
            WORKINGPATH = C['WORKINGPATH']
            CMDS = CommandsPy(console=C['CONSOLE'], cwd=WORKINGPATH)
            C['CMDS'] = CMDS
            Paths.makeFolder(WORKINGPATH)
        except:
            pass

        # Call method in a new thread
        if(C['CALLBACK']):
            callback = getattr(self, C['CALLBACK'])
            action_thread = threading.Thread(target=callback)
            action_thread.start()
            ThreadProgress(action_thread, _('processing'), _('done'))

    def initProject(self):
        """
        Initializes the PlatformIO project with selected environment
        """

        # check if it was already initialized (stop execution if it was)
        CMD = C['CMDS']
        NATIVE = C['NATIVE']
        ENVIRONMENT = C['ENVIRONMENT']
        INIFILE = ConfigObj(C['INIPATH'])

        # checks if the environment was previously initialized
        for env in INIFILE:
            if(ENVIRONMENT in env):
                return None

        # Run Command
        command = ['init', '-b %s' % (ENVIRONMENT)]
        CMD.runCommand(command, "init_project_{0}")

        # structure the project as native or not native
        if(not CMD.error_running):
            if(NATIVE):
                CURRENTPATH = C['SKETCHDIR']
                FILENAME = C['FILENAME']
                NEWPATH = os.path.join(CURRENTPATH, 'src', FILENAME)

                self.window.run_command('close_file')
                move(C['SKETCHPATH'], NEWPATH)
                self.window.open_file(NEWPATH)
            else:
                self.overrideSrc()

    def build(self):
        """
        Build the file in the current view using PlatformIO CLI. It first
        checks if the current environment was previously initialized
        """
        if(not C['IOT']):
            return

        CMD = C['CMDS']

        self.message_queue = MessageQueue(C['CONSOLE'])
        self.message_queue.startPrint()
        self.message_queue.put(
            '[ Deviot {0} ] {1}\\n', version, C['FILENAME'])

        # initialize the sketch
        self.initProject()

        # stop if there is an error
        if(CMD.error_running):
            return

        command = ['run', '-e %s' % C['ENVIRONMENT']]
        CMD.runCommand(command, "built_project_{0}")

        C['BUILT'] = True
        if(CMD.error_running):
            C['BUILT'] = False

    def upload(self):
        """
        Upload the current file to the select hardware, it checks if any
        programmer option was previously selected
        """
        if(not C['IOT']):
            return

        CMD = C['CMDS']

        PORT = C['PORT']
        ENVIRONMENT = C['ENVIRONMENT']

        # check ota only for Espressif
        mdns = self.mDNSCheck()
        if(not mdns):
            return

        # Stop serial monitor
        Tools.closeSerialMonitors()

        self.message_queue = MessageQueue(C['CONSOLE'])
        self.message_queue.startPrint()
        self.message_queue.put(
            '[ Deviot {0} ] {1}\\n', version, C['FILENAME'])

        # initialize the sketch
        self.initProject()

        # add ota auth
        if(not C['AUTH']):
            Preferences().set('auth', '0')
        self.authOTA()

        # get programmer preference
        programmer = Preferences().get("programmer", False)

        # Create command
        if("teensy" in ENVIRONMENT):
            command = ['run', '-t', 'upload', '-e', '%s' % (ENVIRONMENT)]
        elif(not programmer):
            command = ['run', '-t', 'upload', '--upload-port %s -e %s' %
                       (PORT, ENVIRONMENT)]
        else:
            command = ['run', '-t', 'program', '-e', '%s' % (ENVIRONMENT)]

        # add the programmer option
        self.programmer(programmer)

        # run command
        return
        CMD.runCommand(command, "uploading_firmware_{0}")

        # start the monitor serial if was running previously
        if(not CMD.error_running):
            autorun = Preferences().get('autorun_monitor', False)
            if(autorun):
                Tools.toggleSerialMonitor()
                Preferences().set('autorun_monitor', False)
        self.message_queue.stopPrint()

    def clean(self):
        """
        Remove the cached compiled files for the chosen environment
        """
        if(not C['IOT']):
            return

        CMD = C['CMDS']

        command = ['run', '-t', 'clean', '-e', '%s' % (C['ENVIRONMENT'])]
        CMD.runCommand(command, "clean_built_files__{0}")

    def selectPort(self):
        """
        Shows the quick panel with the list of all ports currently available

        """

        from .JSONFile import JSONFile
        quick_path = Paths.getTemplateMenuPath('serial.json', user_path=True)
        serial = JSONFile(quick_path)

        quickPanel(serial.data, self.savePortCallback,
                   index=C['PORTINDEX'])

    def saveBoardCallback(self, selected):
        """
        Callback to save the chosen option by the user in the preferences file

        Arguments:
            selected {int} -- index with the choosen option
        """
        if(selected != -1):
            choose = Menu().createBoardsMenu()
            board_id = choose[selected][1].split(' | ')[1]
            Preferences().boardSelected(board_id)
            Tools.saveEnvironment(board_id)
            Tools.userPreferencesStatus()
            self.beforeProcess(C['CALLBACK'])

    def saveEnvironmetCallback(self, selected):
        """
        Callback to save the chosen option by the user in the preferences file

        Arguments:
            selected {int} -- index with the choosen option
        """
        if(selected != -1):
            list = Menu().getEnvironments()
            env = list[0][selected][1].split(' | ')[1]
            Tools.saveEnvironment(env)
            Tools.userPreferencesStatus()
            C['ENVIRONMENT'] = env
            self.beforeProcess(C['CALLBACK'])

    def savePortCallback(self, selected):
        """
        Callback to save the chosen option by the user in the preferences file

        Arguments:
            selected {int} -- index with the choosen option
        """
        if(selected > 0):
            if(selected == 1):
                self.window.run_command('add_serial_ip')
            from .JSONFile import JSONFile
            quick_path = Paths.getTemplateMenuPath(
                'serial.json', user_path=True)
            serial = JSONFile(quick_path)
            C['PORTSLIST'] = serial.data
            choose = serial.data
            id_port = choose[selected][0]
            C['C'] = id_port
            Preferences().set('id_port', id_port)
            Tools.userPreferencesStatus()

            if(C['CALLBACK'] == 'upload'):
                callback = getattr(self, C['CALLBACK'])
                self.beforeProcess(callback)

    def overrideSrc(self):
        """
        Append in the platformio.ini file, the src_dir option
        to override the source folder where the sketch is stored
        (when the file haven't PlatformIO structure)
        """

        INIFILE = ConfigObj(C['INIPATH'])
        source = {'src_dir': C['SKETCHDIR']}
        INIFILE['platformio'] = source
        INIFILE.write()

    def programmer(self, programmer):
        """
        Adds the programmer strings in the platformio.ini file, it considerate
        environment and programmer selected

        Arguments:
            programmer {str} -- id of chosen option
        """

        # list of programmers
        flags = {
            'avr':          {"upload_protocol": "stk500v1",
                             "upload_flags": "-P$UPLOAD_PORT",
                             "upload_port": C['PORT']},
            'avrmkii':      {"upload_protocol": "stk500v2",
                             "upload_flags": "-Pusb"},
            'usbtyni':      {"upload_protocol": "usbtiny"},
            'arduinoisp':   {"upload_protocol": "arduinoisp"},
            'usbasp':       {"upload_protocol": "usbasp",
                             "upload_flags": "-Pusb"},
            'parallel':     {"upload_protocol": "dapa",
                             "upload_flags": "-F"},
            'arduinoasisp': {"upload_protocol": "stk500v1",
                             "upload_flags": "-P$UPLOAD_PORT -b$UPLOAD_SPEED",
                             "upload_speed": "19200",
                             "upload_port": C['PORT']}
        }

        INIFILE = ConfigObj(C['INIPATH'])
        ENVIRONMENT = 'env:%s' % C['ENVIRONMENT']
        ENV = INIFILE[ENVIRONMENT]

        rm = ['upload_protocol', 'upload_flags', 'upload_speed', 'upload_port']

        # remove previous configuration
        for line in rm:
            if(line in ENV):
                ENV.pop(line)

        # add programmer option if it was selected
        if(programmer):
            ENV.merge(flags[programmer])

        # save in file
        INIFILE.write()

    def getMCU(self):
        """
        Give the MCU for the current board selected
        Returns:
            [str] -- MCU type/name
        """

        # get data from user preference file
        type_env = Tools.getTypeEnvironment()
        environment = Preferences().get(type_env, False)
        env_data = Menu().getTemplateMenu(file_name='platformio_boards.json',
                                          user_path=True)
        env_data = json.loads(env_data)

        try:
            selected = env_data[environment]['build']['mcu']
        except:  # PlatformIO 3
            selected = env_data[0]['mcu']

        return selected

    def authOTA(self):
        """
        Adds OTA authentication (password) in the platformio.ini file
        based in the current environment chosen

        Arguments:
            password {str} -- password
        """
        password = Preferences().get('auth', False)
        INIFILE = ConfigObj(C['INIPATH'])
        ENVIRONMENT = 'env:%s' % C['ENVIRONMENT']

        # remove flag
        if(password or password == '0'):
            if('upload_flags' in INIFILE[ENVIRONMENT]):
                INIFILE[ENVIRONMENT].pop('upload_flags')
                INIFILE.write()
            return

        # Write flag
        FLAG = {'upload_flags': '--auth=%s' % password}
        INIFILE[ENVIRONMENT].merge(FLAG)
        INIFILE.write()

    def mDNSCheck(self, feedback=True):
        """
        When a mDNS service is selected, allows to upload only espressif
        platforms, it's the only type of platform available to to OTA upload

        Returns:
            bool -- True if is possible to upload, False if isn't
        """
        is_native = Preferences().get('native')
        type_env = "env_selected" if not is_native else "native_env_selected"
        environment = Preferences().get(type_env, False)
        port = Preferences().get('id_port', False)

        if(not environment or not port):
            return False

        mcu = self.getMCU()

        if(port and "COM" not in port and "esp" not in mcu):
            if(feedback):
                self.message_queue = MessageQueue(C['CONSOLE'])
                self.message_queue.startPrint()
                self.message_queue.put('[ Deviot {0} ] {1}\\n',
                                       version,
                                       C['FILENAME'])
                self.message_queue.put('ota_error_platform')
            return False
        return True

    def saveAuthPassword(self, password):
        """
        Saves the password in the preferences file to OTA uploads

        Arguments:
            password {str} -- password
        """
        Preferences().set('auth', password)
        self.openInThread('upload')

    def openInThread(self, func, join=False):
        """
        Function to open function/methods like build/upload/clean/ports and
        others in a new thread.

        Arguments:
            func {str/obj} -- If It's string, it calls beforeProcess first.
                                when isn't call the object directly
            join {bool} -- use thread.join when it's True (default: {False})
        """
        if(type(func) is str):
            thread = threading.Thread(target=self.beforeProcess, args=(func,))
            thread.start()
        else:
            thread = threading.Thread(target=func)
            thread.start()
            if(join):
                thread.join()
        ThreadProgress(thread, _('processing'), _('done'))

    def saveCodeInFile(self, view):
        """
        If the sketch in the current view has been not saved, it generate
        a random name and stores in a temp folder.

        Arguments: view {ST Object} -- Object with multiples options of ST
        """
        ext = '.ino'

        tmp_path = Paths.getTempPath()
        file_name = str(time.time()).split('.')[0]
        file_path = os.path.join(tmp_path, file_name)
        file_path = os.path.join(file_path, 'src')
        os.makedirs(file_path)

        full_path = file_name + ext
        full_path = os.path.join(file_path, full_path)

        region = sublime.Region(0, view.size())
        text = view.substr(region)
        file = JSONFile(full_path)
        file.writeFile(text)

        view.set_scratch(True)
        window = view.window()
        window.run_command('close')
        view = window.open_file(full_path)

        return (True, view)

    def listSerialPorts(self):
        """
        Get the list of port currently available from PlatformIO CLI
        Returns:
            [list] -- all ports available
        """
        from . import Serial

        lista = [[_('select_port_list'), ""], [_('menu_add_ip'), ""]]

        index = 1
        current_port = Preferences().get('id_port', False)

        # serial ports
        serial = Serial.listSerialPorts()
        if(serial):
            for port in serial:
                index += 1
                lista.append([port, ""])
                if(current_port and current_port == port):
                    C['PORTINDEX'] = index

        # mdns services
        mdns = Serial.listMdnsServices()
        if(mdns):
            for service in mdns:
                index += 1
                try:
                    service = json.loads(service)
                    one = service["server"][:-1]
                    two = service["properties"]["board"]
                    if(current_port and current_port == one):
                        C['PORTINDEX'] = index

                    lista.append([one, two])
                except:
                    pass
        if(len(lista) == 2):
            lista = [[_('menu_none_serial_mdns'), ""], [_('menu_add_ip'), ""]]

        # save ports
        from .JSONFile import JSONFile
        quick_path = Paths.getTemplateMenuPath('serial.json', user_path=True)
        serial = JSONFile(quick_path)
        serial.setData(lista)
        serial.saveData()

        C['PORTSLIST'] = lista
        if(C['CALLBACK'] is not 'upload'):
            self.selectPort()

    def getAPIBoards(self):
        '''
        Get the list of boards from platformIO API using CLI.
        To know more info about platformIO visit:  http://www.platformio.org/

        Returns: {json object} -- list with all boards in a JSON format
        '''
        Tools.setStatus(_('updating_board_list'))

        boards = []
        Run = CommandsPy()

        command = ['boards', '--json-output']
        boards = Run.runCommand(command, setReturn=True)

        Tools.setStatus(_('Done'), erase_time=4000)

        Menu().saveTemplateMenu(
            data=boards, file_name='platformio_boards.json', user_path=True)


def generateFiles():
    """
    It calls the functions and methods to create the main menu, completions
    and syntax file
    """

    Menu().createMainMenu()
    Tools.createCompletions()
    Tools.createSyntaxFile()
