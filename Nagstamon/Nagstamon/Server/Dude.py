#!/usr/bin/python
# -*- encoding: utf-8; py-indent-offset: 4 -*-

import sys
import urllib
import webbrowser
import base64
import time
import datetime

from Nagstamon import Actions
from Nagstamon.Objects import *
from Nagstamon.Server.Generic import GenericServer

class DudeServer(GenericServer):
    TYPE = 'Dude'

    DISABLED_CONTROLS = ["label_monitor_cgi_url",
                         "input_entry_monitor_cgi_url",
                         "input_checkbutton_use_display_name_host",
                         "input_checkbutton_use_display_name_service"]

    def __init__(self, **kwds):
        GenericServer.__init__(self, **kwds)

    def _get_status(self):
        self.new_hosts = dict()
        
        cgi_data = urllib.urlencode([("process", 'login'),\
                                     ("page", 'start'),\
                                     ("user", self.username),\
                                     ("password", self.password)])
        result = self.FetchURL(self.monitor_url+'/dude/main.html', giveback="raw", cgi_data=cgi_data)
        result = self.FetchURL(self.monitor_url+'/dude/main.html?page=devices')
        
        table = result.result('table', {'class': 'tbl'})[0]
        if len(table('tbody')) == 0 :
            trs = table('tr', {'style': 'background: #ffc0c0;'}, recursive=False)
        else :
            tbody = table('tbody')[0]
            trs = tbody('tr', recursive=False)
        trs.pop(0)
        for tr in trs :
            if len(tr('td', recursive=False)) > 1 :
                n = dict()
                tds = tr('td', recursive=False)
                try :
                    n["host"] = str(tds[0].a.string)
                except :
                    n["host"] = 'xxxxx'
                try :
                    n["map"] = str(tds[3].a.string)
                except :
                    n["map"] = 'xxxxx'

                new_host = n["host"]
                self.new_hosts[new_host] = GenericHost()
                self.new_hosts[new_host].name = n["host"]
                self.new_hosts[new_host].status = 'DOWN'
                self.new_hosts[new_host].last_check = 'n/a'
                self.new_hosts[new_host].duration = 'n/a'
                self.new_hosts[new_host].attempt = 'n/a'
                self.new_hosts[new_host].status_information = n["map"]
                self.new_hosts[new_host].site = 'n/a'
                self.new_hosts[new_host].address = 'n/a'
        
        self.isChecking = False
        return Result()
