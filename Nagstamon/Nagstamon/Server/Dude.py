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
        result = self.FetchURL(self.monitor_url+'/dude/main.html?page=devices')
        
        tables = result.result('table', {'class': 'tbl'}) 
        if len(tables) == 0 :
          result = self.FetchURL(self.monitor_url+'/dude/main.html', giveback="raw", cgi_data=cgi_data)
          result = self.FetchURL(self.monitor_url+'/dude/main.html?page=devices')
          tables = result.result('table', {'class': 'tbl'}) 

        table = tables[0]
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
                try :
                    n["deviceinfo_url"] = str(tds[0].a['href'])
                except :
                    n["deviceinfo_url"] = 'xxxxx'

                new_host = n["host"]
                self.new_hosts[new_host] = GenericHost()
                self.new_hosts[new_host].name = n["host"]
                self.new_hosts[new_host].status = 'DOWN'
                self.new_hosts[new_host].last_check = 'n/a'
                self.new_hosts[new_host].duration = 'n/a'
                self.new_hosts[new_host].attempt = 'n/a'
                self.new_hosts[new_host].status_information = n["map"] 
                self.new_hosts[new_host].site = 'n/a'
                self.new_hosts[new_host].deviceinfo_url = n["deviceinfo_url"]
                #self.new_hosts[new_host].address = n["address"]
        
        self.isChecking = False
        return Result()

    def GetHost(self, host):
        if str(self.conf.connect_by_host) == "True":
            return Result(result=host)

        result = self.FetchURL(self.monitor_url+self.hosts[host].deviceinfo_url)
        address = result.result('input', {'name': 'address'})[0]['value']
        return Result(result=address)
