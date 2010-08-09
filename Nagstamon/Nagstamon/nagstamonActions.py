# encoding: utf-8

import threading
import gobject
import time
import datetime
import urllib
import webbrowser
import nagstamonObjects
import commands
import re
# if running on windows import winsound
import platform
if platform.system() == "Windows":
    import winsound

# Garbage collection
import gc

# import for MultipartPostHandler.py which is needed for Opsview downtime form
import urllib2
import mimetools, mimetypes
import os, stat

# import hashlib for centreon url autologin encoding
import hashlib

# flag which indicates if already rechecking all
RecheckingAll = False


def StartRefreshLoop(servers=None, output=None, conf=None):
    """
    the everlasting refresh cycle - starts refresh cycle for every server as thread
    """
    for server in servers.values():
        if str(conf.servers[server.name].enabled) == "True":
            server.thread = RefreshLoopOneServer(server=server, output=output, conf=conf)
            server.thread.start()
            

class RefreshLoopOneServer(threading.Thread):
    """
    one thread for one server per loop
    """
    # kind of a stop please flag, if set to True run() should run no more
    stopped = False
    # Check flag, if set and thread recognizes do a refresh, set to True at the beginning
    doRefresh = True
    # Update interval counter
    count = 0
    
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        # include threading mechanism
        threading.Thread.__init__(self, name=self.server.name)
        self.setDaemon(1)


    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        

    def run(self):  
        """
        loop until end of eternity or until server is stopped
        """
        while self.stopped == False:          
            # check if we have to leave update interval sleep
            if self.count > int(self.conf.update_interval)*60: self.doRefresh = True
            
            # self.doRefresh could also been changed by RefreshAllServers()
            if self.doRefresh == True:
                # check if server is already checked
                if self.server.isChecking == False:              
                    # set server status for status field in popwin
                    self.server.status = "Refreshing"
                    gobject.idle_add(self.output.popwin.UpdateStatus, self.server)
                    # get current status
                    server_status = self.server.GetStatus()
    
                    # debug
                    if str(self.conf.debug_mode) == "True":
                        print self.server.name, ": server return value :", server_status 

                    if server_status == "ERROR":
                        # set server status for status field in popwin
                        self.server.status = "ERROR - please check settings/network"
                        gobject.idle_add(self.output.popwin.UpdateStatus, self.server)
                        # tell gobject to care about GUI stuff - refresh display status
                        # use a flag to prevent all threads at once to write to statusbar label in case
                        # of lost network connectivity - this leads to a mysterious pango crash
                        if self.output.statusbar.isShowingError == False:
                            gobject.idle_add(self.output.RefreshDisplayStatus)
                            # wait a moment
                            time.sleep(5)
                            # change statusbar to the following error message
                            # show error message in statusbar
                            gobject.idle_add(self.output.statusbar.ShowErrorMessage, self.server.status)
                            # wait some seconds
                            time.sleep(5) 
                            # set statusbar error message status back
                            self.output.statusbar.isShowingError = False
                            
                        # wait a moment
                        time.sleep(10)
                            
                        # do some cleanup
                        gc.collect()

                    else:
                        # set server status for status field in popwin
                        self.server.status = "Connected"
                        # tell gobject to care about GUI stuff - refresh display status
                        gobject.idle_add(self.output.RefreshDisplayStatus)
                        # do some cleanup
                        gc.collect()
                        # wait for the doRefresh flag to be True, if it is, do a refresh
                        if self.doRefresh == True:
                            if str(self.conf.debug_mode) == "True":
                                print self.server.name, ":", "Refreshing output - server is already checking:", self.server.isChecking         
                            try:
                                # check if server is already checked
                                if self.server.isChecking == False:
                                    # set server status for status field in popwin
                                    self.server.status = "Refreshing"
                                    gobject.idle_add(self.output.popwin.UpdateStatus, self.server)
                                    # get current status of one given server
                                    server_status = self.server.GetStatus()
                                    # set server status for status field in popwin
                                    if server_status == "ERROR":
                                        self.server.status = "ERROR - please check settings/network"
                                    else:
                                        self.server.status = "Connected"
                                    # tell gobject to care about GUI stuff - refresh display status
                                    gobject.idle_add(self.output.RefreshDisplayStatus)
                                    # do some cleanup
                                    gc.collect()
                            except:
                                pass
                            
                            # reset refresh flag
                            self.doRefresh = False
                            # reset counter
                            self.count = 0           
            else:
                # sleep and count
                time.sleep(2)
                self.count += 2

        
    def Stop(self):
        # simply sets the stopped flag to True to let the above while stop this thread when checking next
        self.stopped = True
        
        
    def Refresh(self):
        # simply sets the stopped flag to True to let the above while stop this thread when checking next
        self.doRefresh = True

                    
def RefreshAllServers(servers=None, output=None, conf=None):
    """
    one refreshing action, starts threads, one per polled server
    """    
    for server in servers.values():        
        # check if server is already checked
        if server.isChecking == False and str(conf.servers[server.name].enabled) == "True":
            #debug
            if str(conf.debug_mode) == "True":
                print "Checking server:", server.name
    
            server.thread.Refresh()

            # set server status for status field in popwin
            server.status = "Refreshing"
            gobject.idle_add(output.popwin.UpdateStatus, server)
            
    # do some cleanup
    gc.collect()
    

class Recheck(threading.Thread):
    """
    recheck a clicked service/host
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self, name=self.server.name + "-Recheck")
        self.setDaemon(1)
        

    def run(self):
        try:
            # decision about host or service - they have different URLs
            if self.service == None:
                # host
                # get start time from Nagios as HTML to use same timezone setting like the locally installed Nagios
                html = self.server.FetchURL(self.server.nagios_cgi_url + "/cmd.cgi?" + urllib.urlencode({"cmd_typ":"96", "host":self.host}), giveback="raw")
                start_time = html.split("NAME='start_time' VALUE='")[1].split("'></b></td></tr>")[0]
                # fill and encode CGI data
                cgi_data = urllib.urlencode({"cmd_typ":"96", "cmd_mod":"2", "host":self.host, "start_time":start_time, "force_check":"on", "btnSubmit":"Commit"})
            else:
                # service @ host
                # get start time from Nagios as HTML to use same timezone setting like the locally instaled Nagios
                html = self.server.FetchURL(self.server.nagios_cgi_url + "/cmd.cgi?" + urllib.urlencode({"cmd_typ":"7", "host":self.host, "service":self.service}), giveback="raw")
                start_time = html.split("NAME='start_time' VALUE='")[1].split("'></b></td></tr>")[0]
                # fill and encode CGI data
                cgi_data = urllib.urlencode({"cmd_typ":"7", "cmd_mod":"2", "host":self.host, "service":self.service, "start_time":start_time, "force_check":"on", "btnSubmit":"Commit"})

            # execute POST request
            self.server.FetchURL(self.server.nagios_cgi_url + "/cmd.cgi", giveback="nothing", cgi_data=cgi_data)

        except:
            pass
        

    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        
        
class RecheckAll(threading.Thread):
    """
    recheck all services/hosts
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self, name="RecheckAll")
        self.setDaemon(1)
        

    def run(self):
        
        # get RecheckingAll flag to decide if rechecking all is possible (only if not already running)
        global RecheckingAll
        
        if RecheckingAll == False:
            RecheckingAll = True
            # put all rechecking threads into one dictionary
            rechecks_dict = dict()
            try:
                # debug
                if str(self.conf.debug_mode) == "True":
                    print "Recheck all: Rechecking all services on all hosts on all servers..."
                    
                for server in self.servers.values():
                    # only test enabled servers and only if not already 
                    if str(self.conf.servers[server.name].enabled):
                        # set server status for status field in popwin
                        server.status = "Rechecking all started"
                        gobject.idle_add(self.output.popwin.UpdateStatus, server)
                        
                        for host in server.hosts.values():
                            # construct an unique key which refers to rechecking thread in dictionary
                            rechecks_dict[server.name + ": " + host.name] = Recheck(server=server, host=host.name, service=None)
                            rechecks_dict[server.name + ": " + host.name].start()
                            # debug
                            if str(self.conf.debug_mode) == "True":
                                print "Recheck all:", "rechecking", server.name + ": " + host.name
                            for service in host.services.values():
                                # dito
                                rechecks_dict[server.name + ": " + host.name + ": " + service.name] = Recheck(server=server, host=host.name, service=service.name)
                                rechecks_dict[server.name + ": " + host.name + ": " + service.name].start()
                                # debug
                                if str(self.conf.debug_mode) == "True":
                                    print "Recheck all:", "rechecking", server.name + ": " + host.name + ": " + service.name
                
                # wait until all rechecks have been done
                while len(rechecks_dict) > 0:
                    # debug
                    if str(self.conf.debug_mode) == "True":
                        print "Recheck all: # of checks which still need to be done:", len(rechecks_dict)
                    
                    for i in rechecks_dict.copy():
                        # if a thread is stopped pop it out of the dictionary
                        if rechecks_dict[i].isAlive() == False:
                            rechecks_dict.pop(i)
                    # wait a second        
                    time.sleep(1)
                    
                # debug
                if str(self.conf.debug_mode) == "True":
                    print "Recheck all: All servers, hosts and services are rechecked."
                
                # reset global flag
                RecheckingAll = False
                
                # after all and after a short delay to let Nagios apply the recheck requests refresh all to make changes visible soon
                time.sleep(5)
                RefreshAllServers(servers=self.servers, output=self.output, conf=self.conf)
                # do some cleanup
                del rechecks_dict
                gc.collect()
                               
            except:
                RecheckingAll = False
                pass
           
        else:
            # debug
            if str(self.conf.debug_mode) == "True":
                print "Recheck all: Already rechecking all services on all hosts on all servers."
                
        
    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        
        
class Acknowledge(threading.Thread):
    """
    exceute remote cgi command with parameters from acknowledge dialog 
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self)
        self.setDaemon(1)

    def run(self):
        url = self.server.nagios_cgi_url + "/cmd.cgi"
        # decision about host or service - they have different URLs
        # do not care about the doube %s (%s%s) - its ok, "flags" cares about the necessary "&"
        if self.service == "":
            # host
            cgi_data = urllib.urlencode({"cmd_typ":"33", "cmd_mod":"2", "host":self.host, "com_author":self.author, "com_data":self.comment, "btnSubmit":"Commit"})

        else:
            # service @ host
            cgi_data = urllib.urlencode({"cmd_typ":"34", "cmd_mod":"2", "host":self.host, "service":self.service, "com_author":self.author, "com_data":self.comment, "btnSubmit":"Commit"})

        # running remote cgi command        
        self.server.FetchURL(url, giveback="nothing", cgi_data=cgi_data)

        # acknowledge all services on a host
        if self.acknowledge_all_services == True:
            for s in self.all_services:
                # service @ host
                cgi_data = urllib.urlencode({"cmd_typ":"34", "cmd_mod":"2", "host":self.host, "service":s, "com_author":self.author, "com_data":self.comment, "btnSubmit":"Commit"})
                #running remote cgi command        
                self.server.FetchURL(url, giveback="nothing", cgi_data=cgi_data)

        
    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        
    
class Downtime(threading.Thread):
    """
    exceute remote cgi command with parameters from acknowledge dialog 
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self)
        self.setDaemon(1)

    def run(self):
        if self.server.type == "Opsview":
            # get action url for opsview downtime form
            if self.service == "":
                # host
                cgi_data = urllib.urlencode({"cmd_typ":"55", "host":self.host})
            else:
                # service
                cgi_data = urllib.urlencode({"cmd_typ":"56", "host":self.host, "service":self.service})
            url = self.server.nagios_cgi_url + "/cmd.cgi"
            html = self.server.FetchURL(url, giveback="raw", cgi_data=cgi_data)
            # which opsview form action to call
            action = html.split('" enctype="multipart/form-data">')[0].split('action="')[-1]
            # this time cgi_data does not get encoded because it will be submitted via multipart
            # to build value for hidden from field old cgi_data is used
            cgi_data = { "from" : url + "?" + cgi_data, "comment": self.comment, "starttime": self.start_time, "endtime": self.end_time }
            self.server.FetchURL(self.server.nagios_url + action, giveback="nothing", cgi_data=cgi_data)
        else:
            # decision about host or service - they have different URLs
            if self.service == "":
                # host
                cgi_data = urllib.urlencode({"cmd_typ":"55","cmd_mod":"2","trigger":"0","childoptions":"0","host":self.host,"com_author":self.author,"com_data":self.comment,"fixed":self.fixed,"start_time":self.start_time,"end_time":self.end_time,"hours":self.hours,"minutes":self.minutes,"btnSubmit":"Commit"})
            else:
                # service @ host
                cgi_data = urllib.urlencode({"cmd_typ":"56","cmd_mod":"2","trigger":"0","childoptions":"0","host":self.host,"service":self.service,"com_author":self.author,"com_data":self.comment,"fixed":self.fixed,"start_time":self.start_time,"end_time":self.end_time,"hours":self.hours,"minutes":self.minutes,"btnSubmit":"Commit"})
            url = self.server.nagios_cgi_url + "/cmd.cgi"
        
            # running remote cgi command
            self.server.FetchURL(url, giveback="nothing", cgi_data=cgi_data)
            

    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        

def Downtime_get_start_end(server, host):
    # get start and end time from Nagios as HTML - the objectified HTML does not contain the form elements :-(
    # this used to happen in GUI.action_downtime_dialog_show but for a more strict separation it better stays here
    html = server.FetchURL(server.nagios_cgi_url + "/cmd.cgi?" + urllib.urlencode({"cmd_typ":"55", "host":host}), giveback="raw")

    if server.type == "Opsview":
        start_time = html.split('name="starttime" value="')[1].split('"')[0]
        end_time = html.split('name="endtime" value="')[1].split('"')[0]        
    else:
        start_time = html.split("NAME='start_time' VALUE='")[1].split("'></b></td></tr>")[0]
        end_time = html.split("NAME='end_time' VALUE='")[1].split("'></b></td></tr>")[0]
        
    # give values back as tuple
    return start_time, end_time
        

class CheckForNewVersion(threading.Thread):
    """
        Check for new version of nagstamon using connections of configured servers 
    """    
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self)
        self.setDaemon(1)
        
    
    def run(self):
        # try all servers respectively their net connections, one of them should be able to connect
        # to nagstamon.sourceforge.net
        
        # debug
        if str(self.output.conf.debug_mode) == "True":
           print "Checking for new version..."
        
        for s in self.servers.values():
            # if connecton of a server is not yet used do it now
            if s.CheckingForNewVersion == False:
                # set the flag to lock that connection
                s.CheckingForNewVersion = True
                # remove newline
                version = s.FetchURL("http://nagstamon.sourceforge.net/latest_version", giveback="raw").split("\n")[0]
                
                # debug
                if str(self.output.conf.debug_mode) == "True":
                   print "Latest version from sourceforge.net:", version
                
                # if we got a result notify user
                if version != "ERROR":
                    if version == self.output.version:
                        version_status = "latest"
                    else:
                        version_status = "out_of_date"
                    # if we got a result reset all servers checkfornewversion flags, 
                    # notify the user and break out of the for loop
                    for s in self.servers.values(): s.CheckingForNewVersion = False
                    # do not tell user that the version is latest when starting up nagstamon
                    if not (self.mode == "startup" and version_status == "latest"):
                        # gobject.idle_add is necessary to start gtk stuff from thread
                        gobject.idle_add(self.output.CheckForNewVersionDialog, version_status, version) 
                    break
                # reset the servers CheckingForNewVersion flag to allow a later check
                s.CheckingForNewVersion = False


    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
    

class PlaySound(threading.Thread):
    """
        play notification sound in a threadified way to omit hanging gui
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self)
        self.setDaemon(1)


    def run(self):
        if self.sound == "WARNING":
            if str(self.conf.notification_default_sound) == "True":
                self.Play(self.Resources + "/warning.wav")
            else:
                self.Play(self.conf.notification_custom_sound_warning)
        elif self.sound == "CRITICAL":
            if str(self.conf.notification_default_sound) == "True":
                self.Play(self.Resources + "/critical.wav")
            else:
                self.Play(self.conf.notification_custom_sound_critical)
        elif self.sound == "DOWN":
            if str(self.conf.notification_default_sound) == "True":
                self.Play(self.Resources + "/hostdown.wav")
            else:
                self.Play(self.conf.notification_custom_sound_down)
        elif self.sound =="FILE":
            self.Play(self.file)
    
    
    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)
        
    
    def Play(self, file):
        """
            depending on platform choose method to play sound
        """
        # debug
        if str(self.conf.debug_mode) == "True":
            print "Playing sound:", file
        try:
            if not platform.system() == "Windows":
                commands.getoutput("play -q %s" % file)
            else:
                winsound.PlaySound(file, winsound.SND_FILENAME)
        except:
            pass
            
                    
class FlashStatusbar(threading.Thread):
    """
        Flash statusbar in a threadified way to omit hanging gui
    """
    def __init__(self, **kwds):
        # add all keywords to object, every mode searchs inside for its favorite arguments/keywords
        for k in kwds: self.__dict__[k] = kwds[k]
        threading.Thread.__init__(self)
        self.setDaemon(1)


    def run(self):
        # in case of notifying in statusbar do some flashing
        try:
            if self.output.Notifying == True:
                # as long as flashing flag is set statusbar flashes until someone takes care
                while self.output.statusbar.Flashing == True:
                    if self.output.statusbar.isShowingError == False:
                        # check again because in the mean time this flag could have been changed by NotificationOff()
                        gobject.idle_add(self.output.statusbar.Flash)
                        time.sleep(0.5)
            # reset statusbar
            self.output.statusbar.Label.set_markup(self.output.statusbar.statusbar_labeltext)
        except:
            pass


    def __del__(self):
        """
        hopefully a __del__() method may make this object better collectable for gc
        """
        del(self)


def OpenNagios(widget, server, output):
    # open Nagios main page in your favorite web browser when nagios button is clicked
    # first close popwin
    output.popwin.Close()
    # start browser with URL
    if server.type == "Centreon":
        webbrowser.open(server.nagios_url + "/main.php?autologin=1&useralias=" + MD5ify(server.username) + "&password=" + MD5ify(server.password))
    else:
        webbrowser.open(server.nagios_url)
    # debug
    if str(output.conf.debug_mode) == "True":
        print server.name, ":", "Open Nagios website", server.nagios_url        


def OpenServices(widget, server, output):
    # open Nagios services in your favorite web browser when service button is clicked
    # first close popwin
    output.popwin.Close()
    # start browser with URL
    if server.type == "Centreon":
        webbrowser.open(server.nagios_url + "/main.php?autologin=1&useralias=" + MD5ify(server.username) + "&password=" + MD5ify(server.password) + "&p=20202&o=svcpb")
        # debug
        if str(output.conf.debug_mode) == "True":
            print server.name, ":", "Open hosts website", server.nagios_url + "/main.php?p=20202&o=svcpb"
    else:
        webbrowser.open(server.nagios_cgi_url + "/status.cgi?host=all&servicestatustypes=253")
        # debug
        if str(output.conf.debug_mode) == "True":
            print server.name, ":", "Open services website", server.nagios_url + "/status.cgi?host=all&servicestatustypes=253"  
 
   
def OpenHosts(widget, server, output):
    # open Nagios hosts in your favorite web browser when hosts button is clicked
    # first close popwin
    output.popwin.Close()
    # start browser with URL
    if server.type == "Centreon":
        webbrowser.open(server.nagios_url + "/main.php?autologin=1&useralias=" + MD5ify(server.username) + "&password=" + MD5ify(server.password) + "&p=20103&o=hpb")
        # debug
        if str(output.conf.debug_mode) == "True":
            print server.name, ":", "Open hosts website", server.nagios_url + "/main.php?p=20103&o=hpb"
    else:
        webbrowser.open(server.nagios_cgi_url + "/status.cgi?hostgroup=all&style=hostdetail&hoststatustypes=12")
        # debug
        if str(output.conf.debug_mode) == "True":
            print server.name, ":", "Open hosts website", server.nagios_url + "/status.cgi?hostgroup=all&style=hostdetail&hoststatustypes=12"      

    
def TreeViewNagios(server, host, service):
    # if the clicked row does not contain a service it mus be a host, 
    # so the nagios query is different 
    if service is None:
        if server.type == "Centreon":
            webbrowser.open(server.nagios_url + "/main.php?autologin=1&useralias=" + MD5ify(server.username) + "&password=" + MD5ify(server.password) + "&p=4&mode=0&svc_id=" + host)
        else:
            webbrowser.open(server.nagios_cgi_url + "/extinfo.cgi?type=1&host=" + host)
    else:
        if server.type == "Centreon":
            webbrowser.open(server.nagios_url + "/main.php?autologin=1&useralias=" + MD5ify(server.username) + "&password=" + MD5ify(server.username) + "&p=4&mode=0&svc_id=" + host + ";" + service)
        else:
            webbrowser.open(server.nagios_cgi_url + "/extinfo.cgi?type=2&host=" + host + "&service=" + service)

        
def TreeViewHTTP(host):
    # open Browser with URL of some Host
    webbrowser.open("http://" + host)
        

def CreateServer(server=None, conf=None):
    # create Server from config
    nagiosserver = nagstamonObjects.NagiosServer(conf=conf)
    nagiosserver.name = server.name
    nagiosserver.type = server.type
    nagiosserver.nagios_url = server.nagios_url
    nagiosserver.nagios_cgi_url = server.nagios_cgi_url
    nagiosserver.username = server.username
    nagiosserver.password = server.password
    nagiosserver.use_proxy = server.use_proxy
    nagiosserver.use_proxy_from_os = server.use_proxy_from_os
    nagiosserver.proxy_address = server.proxy_address
    nagiosserver.proxy_username = server.proxy_username
    nagiosserver.proxy_password = server.proxy_password
    
    # debug
    if str(conf.debug_mode) == "True":
        print "Created Server", server.name

    return nagiosserver


def OpenNagstamonDownload(output=None):
    """
        Opens Nagstamon Download page after being offered by update check
    """
    # first close popwin
    output.popwin.Close()
    # start browser with URL
    webbrowser.open("http://nagstamon.sourceforge.net/download")
       

def HostIsFilteredOutByRE(host, conf=None):
    """
        helper for applying RE filters in nagstamonGUI.RefreshDisplay()
    """
    try:
        if str(conf.re_host_enabled) == "True":
            pattern = re.compile(conf.re_host_pattern)
            result = pattern.findall(host)
            
            if len(result) > 0:
                if str(conf.re_host_reverse) == "True":
                    return False
                else:
                    return True
            else:
                if str(conf.re_host_reverse) == "True":
                    return True
                else:
                    return False
        
        # if RE are disabled return True because host is not filtered      
        return False
    except:
        pass
        
        
def ServiceIsFilteredOutByRE(service, conf=None):
    """
        helper for applying RE filters in nagstamonGUI.RefreshDisplay()
    """
    try:
        if str(conf.re_service_enabled) == "True":
            pattern = re.compile(conf.re_service_pattern)
            result = pattern.findall(service)
            if len(result) > 0:
                if str(conf.re_service_reverse) == "True":
                    return False
                else:
                    return True
            else:
                if str(conf.re_service_reverse) == "True":
                    return True 
                else:
                    return False
        
        # if RE are disabled return True because host is not filtered      
        return False
    except:
        pass
    

def HumanReadableDuration(seconds):
    """
    convert seconds given by Opsview to the form Nagios gives them
    like 70d 3h 34m 34s
    """
    timedelta = str(datetime.timedelta(seconds=int(seconds)))
    try:
        if timedelta.find("days") == -1:
            hms = timedelta.split(":")
            if len(hms) == 1:
                return "0d 0h 0m %ss" % (hms[0])
            elif len(hms) == 2:
                return "0d 0h %sm %ss" % (hms[0], hms[1])
            else:
                return "0d %sh %sm %ss" % (hms[0], hms[1], hms[2])
        else:
            # waste is waste - does anyone nee
            days, waste, hms = str(timedelta).split(" ")
            hms = hms.split(":")
            return "%sd %sh %sm %ss" % (days, hms[0], hms[1], hms[2])
    except:
        # in case of any error return seconds we got
        return seconds
    
    
def MD5ify(string):
    """
    makes something md5y of a given username or password for Centreon web interface access
    """
    return hashlib.md5(string + "\n").hexdigest()
    
       
# <IMPORT>
# Borrowed from http://pipe.scs.fsu.edu/PostHandler/MultipartPostHandler.py
# Released under LGPL
# Thank you Will Holcomb!
class Callable:
    def __init__(self, anycallable):
        self.__call__ = anycallable

        
class MultipartPostHandler(urllib2.BaseHandler):
    handler_order = urllib2.HTTPHandler.handler_order - 10 # needs to run first

    def http_request(self, request):
        data = request.get_data()
        if data is not None and type(data) != str:
            v_vars = []
            try:
                for(key, value) in data.items():
                    v_vars.append((key, value))
            except TypeError:
                systype, value, traceback = sys.exc_info()
                raise TypeError, "not a valid non-string sequence or mapping object", traceback

            boundary, data = self.multipart_encode(v_vars)
            contenttype = 'multipart/form-data; boundary=%s' % boundary
            if(request.has_header('Content-Type')
               and request.get_header('Content-Type').find('multipart/form-data') != 0):
                print "Replacing %s with %s" % (request.get_header('content-type'), 'multipart/form-data')
            request.add_unredirected_header('Content-Type', contenttype)

            request.add_data(data)
        return request

    def multipart_encode(vars, boundary = None, buffer = None):
        if boundary is None:
            boundary = mimetools.choose_boundary()
        if buffer is None:
            buffer = ''
        for(key, value) in vars:
            buffer += '--%s\r\n' % boundary
            buffer += 'Content-Disposition: form-data; name="%s"' % key
            buffer += '\r\n\r\n' + value + '\r\n'
        buffer += '--%s--\r\n\r\n' % boundary
        return boundary, buffer
    
    multipart_encode = Callable(multipart_encode)
    https_request = http_request
    
# </IMPORT>
