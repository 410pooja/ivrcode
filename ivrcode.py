import os,sys
sys.path.insert(0, os.getcwd())

from ivrlib import *
import logging
import logging.handlers
from twisted.enterprise import adbapi
from twisted.internet.protocol import Protocol
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from twisted.mail.smtp import ESMTPSenderFactory
from cStringIO import StringIO
import MySQLdb,MySQLdb.cursors
import httplib
import datetime

config = MyConfigParser()
config.read("/opt/lectureinfo/config.conf")

soundsdir = config.get("paths", "sounds", "lectures/")

smshost = config.get("sms", "host")
smsdb = config.get("sms", "db")
smsuser = config.get("sms", "user")
smspasswd = config.get("sms","passwd")

mailuser= "jay@lintelindia.com"
mailpasswd = "jay@2829"
mailhost = "smtp.lintelindia.com"
mailport = 587
frommail= "jay@lintelindia.com"

ltime=datetime.datetime.now().strftime("%H:%M:%S")
lday= datetime.datetime.now().strftime("%A")

class Lecture(ivrlib):


    def __init__(self, agi):
        """constructor for class Lecture"""
        self.agi = agi
        self.agi.status = "NEW"
        self.context = self.agi.variables['agi_context']
        ivrlib.__init__(self)
        self.initLogger()
        self.agi.onClose().addErrback(self.onHangup) #register a callback to clean up on Hangup.
        self.dbtries = 0
        self.entries=0
        self.agi.enrollment = "None"
        self.times = None
        self.checkenroll()

    def checkenroll(self):
        print self.context
        if self.context == 'enenroll':
            self.agi.execute('Set', 'CHANNEL(language)=en').addCallback(self.collectEnroll)
        elif self.context == 'gjenroll':
            self.agi.execute('Set', 'CHANNEL(language)=de').addCallback(self.collectEnroll)
        elif self.context == 'hnenroll':
            self.agi.execute('Set', 'CHANNEL(language)=fr').addCallback(self.collectEnroll)
        else:
            self.welcome()

    def collectEnroll(self,res):
        print ("In Collect Enroll function")
        cd = CollectDigits(self.agi)
        cd.maxDigits = 12
        cd.prompt = soundsdir + 'please-enter'
        df = cd()
        df.addCallback(self.verifyenroll)

    def verifyenroll(self,option):
        self.agi.enrollment = option
        print self.entries
        if len(str(self.agi.enrollment)) == 12:
            s = fastagi.InSequence()
            s.append(self.agi.sayDigits, option)
            s().addCallback(self.checkstudentdata)
            sql = """SELECT * FROM students WHERE enrollment_number=%s"""
            print sql % str(option)
            df = dbpool.runQuery(sql,self.agi.enrollment)
            df.addCallback(self.checkstudentdata)
        elif self.entries < 2:
            self.entries = self.entries + 1
            print self.entries
            df = self.agi.streamFile(soundsdir+'sorry')
            df.addCallback(self.collectEnroll)
        else:
            df =self.agi.streamFile(soundsdir+'thankyou')
            df.addCallback(self.hangup)

    def checkstudentdata(self,res):
        try:
	    x = res[0]['enrollment_number']
	    print "Your enrollment number is ",x
            print res
            sql = """INSERT INTO students (enrollment_number,mobile_number,indcn,infib,emdcn,emfib,attendance,exam,email) values(%s,%s,%s,%s,%s,%s,%s,%s,%s) """
            df = dbpool.runQuery(sql, (str(self.agi.enrollment), str(self.callerid[-10:]),str( res[0]['indcn']), str(res[0]['infib']),str(res[0]['emdcn']),str(res[0]['emfib']),str(res[0]['attendance']),str(res[0]['exam']),res[0]['email']))
            df.addCallback(self.thankyoureg)
	except:
	    print "We are here...."
	    self.hangup()

    def thankyoureg(self,res):
        df = self.agi.streamFile(soundsdir+'thankyou')
        df.addCallback(self.hangup)

    def welcome(self):
        print ("In Welcome function")
        co = CollectOption(self.agi)
        co.prompt = soundsdir+"welcome"
        co.options = '123'
        df = co()
        df.addCallback(self.setLanguage,self.hangup)

    def setLanguage(self, option,res):
        print option
        if option == '3':
            self.agi.lang = "gj"
            self.log.info("Caller chose Gujarati")
            self.agi.execute('Set', 'CHANNEL(language)=de').addCallbacks(self.checkMainMenu, self.hangup)
        if option == '1':
            self.agi.lang = "en"
            self.log.info("Caller chose English")
            self.agi.execute('Set', 'CHANNEL(language)=en').addCallbacks(self.checkMainMenu, self.hangup)
        if option == '2':
            self.agi.lang = 'hn'
            self.log.info("Caller chose Hindi")
            self.agi.execute('Set', "CHANNEL(language)=fr").addCallbacks(self.checkMainMenu, self.hangup)

    def checkMainMenu(self, option):
        return LectureInfo(self.agi, self.uniqueid)

    def onHangup(self, reason):
        self.log.debug("Call hangup cleaning up")
        self.agi.incall = False
        self.dbtries = 0



class beginBodyCollection(Protocol):
    def __init__(self, finished):
        self.finished = finished
        self.remaining = 1024 * 10
        self.display = None

    def dataReceived(self, bytes):
        """Called whenever data is received.

        Use this method to translate to a higher-level message.  Usually, some
        callback will be made upon the receipt of each complete protocol
        message.

        @param data: a string of indeterminate length.  Please keep in mind
            that you will probably need to buffer some data, as partial
            (or multiple) protocol messages may be received!  I recommend
            that unit tests for protocols call through to this method with
            differing chunk sizes, down to one byte at a time.
        """
        if self.remaining:
            self.display = bytes[:self.remaining]
            self.remaining -= len(display)



    def connectionLost(self, reason):
        """Called when the connection is shut down.

        Clear any circular references here, and any external references
        to this Protocol.  The connection has been closed.

        @type reason: L{twisted.python.failure.Failure}
        """
        self.finished.callback(self.display)

class LectureInfo(ivrlib):


    def __init__(self, agi, uniqueid):
        """constructor for class LectureInfo.
        The self parameter refers to the instance of the object."""
        self.agi = agi
        self.agi.pinconfirm = False
        self.agi.crmcompno = "None"
        self.agi.responsecode = "None"
        self.agi.contact = "None"
        self.agi.enrollment = "None"
        self.agi.indcn=0
        self.agi.infib=0
        self.agi.endcn=0
        self.agi.enfib=0
        self.agi.attendance=0
        self.agi.exam=0
        self.agi.email=None
        self.agi.message=None
        self.uniqueid = uniqueid
        self.URLflag = False
        ivrlib.__init__(self)
        self.initLogger()
        self.CheckReg()
        #self.service()

    def CheckReg(self):
        self.log.debug(self.callerid)
        sql = """SELECT enrollment_number FROM students WHERE mobile_number=%s"""
        df = dbpool.runQuery(sql, (self.callerid[-10:]))
        df.addCallback(self.AskReg)

    def AskReg(self,res):
        print res
        if res:
            self.agi.enrollment = res[0]['enrollment_number']
            self.subMenu()
        else:
            path = '/var/spool/asterisk/outgoing/91%s.call' % self.callerid[-10:]
            file = open(path,'w')
            file.write('Channel: Local/91%s@a1routes\nMaxRetries: 2\nCallerid: +918469285679\nRetryTime: 2\nWaitTime: 45\nContext: %senroll\nExtension: 123\nPriority: 1\nArchive: yes' % (self.callerid[-10:],self.agi.lang))
            file.close()
            df = self.agi.streamFile(soundsdir+'please-register')
            df.addCallback(self.thankyou)


    def subMenu(self):
        co = CollectOption(self.agi)
        co.prompt = soundsdir+"sub-menu"
        co.options = '12345'
        df = co()
        df.addCallback(self.Menu,self.hangup)

    def Menu(self,option,res):
        if option == '1':
            self.internalMarks()
        if option == '2':
            self.externalMarks()
        if option == '3':
            self.attendance()
        if option == '4':
            self.lecturelocation()
        if option == '5':
            self.exam()
    def internalMarks(self):
        sql = """SELECT indcn,infib FROM students WHERE enrollment_number=%s"""
        df = dbpool.runQuery(sql, (self.agi.enrollment))
        df.addCallback(self.sayInternalMarks)

    def sayInternalMarks(self, res):
        print res
        self.agi.indcn= res[0]['indcn']
        self.agi.infib= res[0]['infib']
        self.agi.message = "Internal-Data Communications Network:%s Internal-Fundamentals of Image processing:%s" % (self.agi.indcn,self.agi.infib)
        print self.agi.message
        s = fastagi.InSequence()
        s.append(self.agi.streamFile,soundsdir+'dcn')
        s.append(self.agi.sayDigits, self.agi.indcn)
        s.append(self.agi.streamFile, soundsdir+'fib')
        s.append(self.agi.sayDigits,self.agi.infib)
        s().addCallbacks(self.sendMessage,self.hangup)

    def externalMarks(self):
        sql = """SELECT emdcn,emfib FROM students WHERE enrollment_number=%s"""
        df = dbpool.runQuery(sql, (self.agi.enrollment))
        df.addCallback(self.sayExternalMarks)

    def sayExternalMarks(self, res):
        print res
        self.agi.emdcn= res[0]['emdcn']
        self.agi.emfib= res[0]['emfib']
        self.agi.message = "External-Data Communications Network:%s External-Fundamentals of Image processing:%s" % (self.agi.emdcn,self.agi.emfib)
        s = fastagi.InSequence()
        s.append(self.agi.streamFile,soundsdir+'dcn')
        s.append(self.agi.sayDigits, self.agi.emdcn)
        s.append(self.agi.streamFile, soundsdir+'fib')
        s.append(self.agi.sayDigits,self.agi.emfib)
        s().addCallbacks(self.sendMessage,self.hangup)

    def attendance(self):
        sql = """SELECT attendance FROM students WHERE enrollment_number=%s"""
        df = dbpool.runQuery(sql, (self.agi.enrollment))
        df.addCallback(self.sayattendance)

    def sayattendance(self,res):
        print "Attendance is ", res[0]['attendance']
        self.agi.attendance= res[0]['attendance']
        if self.agi.attendance < '35':
            self.agi.message="You need to atten more lectures, Your attendance is %s" % self.agi.attendance
            s = fastagi.InSequence()
            s.append(self.agi.streamFile,soundsdir+'your-attendance')
            s.append(self.agi.sayDigits, self.agi.attendance)
            s.append(self.agi.streamFile,soundsdir+'percentage')
            s.append(self.agi.streamFile,soundsdir+'low-attendance')
            s().addCallbacks(self.sendMessage, self.hangup)
        else:
            self.agi.message="Your attendance is %s" % self.agi.attendance
            s = fastagi.InSequence()
            s.append(self.agi.streamFile,soundsdir+'your-attendance')
            s.append(self.agi.sayDigits, self.agi.attendance)
            s.append(self.agi.streamFile,soundsdir+'percentage')
            s().addCallbacks(self.sendMessage, self.hangup)

    def lecturelocation(self):
        print lday
        self.agi.message="Wednesday:305 DCN,306 FIP Thursday:306 DCN, 305 FIP Friday:305 DCN,306 FIP"
        if lday in ['Monday','Tuesday','Saturday','Sunday']:
            df = self.agi.streamFile(soundsdir+'nolectures')
            df.addCallback(self.sendMessage)
        if lday == 'Wednesday':
            room1 = '305'
            room2 = '307'
            s = fastagi.InSequence()
            s.append(self.agi.streamFile,soundsdir+'lecture1')
            s.append(self.agi.streamFile,soundsdir+'dcn')
            s.append(self.agi.sayDigits,room1)
            s.append(self.agi.streamFile,soundsdir+'lecture2')
            s.append(self.agi.streamFile,soundsdir+'fib')
            s.append(self.agi.sayDigits,room2)
            s().addCallback(self.sendMessage)
        if lday == 'Thursday':
            room1 = '306'
            room2 = '305'
            s = fastagi.InSequence()
            s.append(self.agi.streamFile,soundsdir+'lecture1')
            s.append(self.agi.streamFile,soundsdir+'dcn')
            s.append(self.agi.sayDigits,room1)
            s.append(self.agi.streamFile,soundsdir+'lecture2')
            s.append(self.agi.streamFile,soundsdir+'fib')
            s.append(self.agi.sayDigits,room2)
            s().addCallback(self.sendMessage)
        if lday == 'Friday':
            room1 = '305'
            room2 = '306'
            s = fastagi.InSequence()
            s.append(self.agi.streamFile,soundsdir+'lecture1')
            s.append(self.agi.streamFile,soundsdir+'dcn')
            s.append(self.agi.sayDigits,room1)
            s.append(self.agi.streamFile,soundsdir+'lecture2')
            s.append(self.agi.streamFile,soundsdir+'fib')
            s.append(self.agi.sayDigits,room2)
            s().addCallback(self.sendMessage)

    def exam(self):
        sql = """SELECT exam FROM students WHERE enrollment_number=%s"""
        df = dbpool.runQuery(sql, (self.agi.enrollment))
        df.addCallback(self.sayexam)

    def sayexam(self,res):
        self.agi.exam=res [0]['exam']
        self.agi.message="Sitting arrangement is in room:%s" % self.agi.exam
        s= fastagi.InSequence()
        s.append(self.agi.streamFile, soundsdir+'exam')
        s.append(self.agi.sayDigits,self.agi.exam)
        s().addCallbacks(self.sendMessage,self.hangup)

    def thankyou(self,res):
        df = self.agi.streamFile(soundsdir+'thankyou')
        df.addCallback(self.hangup)

    def sendMessage(self,option):
        message = self.agi.message
        #message = self.messagefetch()
        print "Message ::"+message
        self.log.debug("Start of Script for number " + self.callerid)
        self.log.debug("sending message to caller ::" + self.callerid)
        connection = httplib.HTTPConnection("smsidea.co.in", port=80)
        message = "/sendsms.aspx?mobile=9898396969&pass=100&senderid=LINTEL&to=" + self.callerid[-10:] + "&msg="+message.replace(' ', '%20')
        print message
        #log.debug(message)
        #message.request("GET", str(message))
        connection.request("GET", message)
        log.debug(message)
        self.log.debug("Getting SMS response for " + self.callerid)
        reply = connection.getresponse()
        readreply = reply.read()
        log.debug("Response from operator is" + readreply)
        df = self.agi.streamFile(soundsdir+'thankyou')
        df.addCallback(self.getemail)

    def getemail(self,option):
        self.hangup()
        log.debug("In get email function")
        sql = """SELECT * FROM students WHERE enrollment_number=%s"""
        print "SELECT * FROM students WHERE enrollment_number=%s" % self.agi.enrollment
        df = dbpool.runQuery(sql, (self.agi.enrollment))
        df.addCallback(self.sendMail)

    def sendMail(self, res):
        log.debug("In sendMail function")
        print res
        self.agi.email= res[0]['email']
        self.agi.indcn= res[0]['indcn']
        self.agi.infib= res[0]['infib']
        self.agi.emdcn= res[0]['emdcn']
        self.agi.emfib= res[0]['emfib']
        self.agi.attendance= res[0]['attendance']
        txt="Hello ,\n\nInternal Marks:\n    Data Communication Network :%(indc)s\n    Fundamental Of Image Processing :%(infp)s\n\nExternal Marks:\n    Data Communication Network :%(emdc)s\n    Fundamental Of Image Processing :%(emfp)s\n\nAttendance :%(att)s\n\nThank you.\n- STUDENT INFORMATION SYSTEM"
        data = {"indc":self.agi.indcn,"infp":self.agi.infib,"emdc":self.agi.emdcn,"emfp":self.agi.emfib,"att":self.agi.attendance}
        msg = MIMEMultipart()
        msg['Subject'] = "University Student Information"
        msg['To'] = self.agi.email
        msg['From'] ="GIT <git@lintelindia.com>"
        textmsg = MIMEText(txt%data)
        msg.attach(textmsg)
        msg = StringIO(msg.as_string())
        df = defer.Deferred()
        df.addCallback(self.hangup)
        f = ESMTPSenderFactory(mailuser, mailpasswd, frommail, self.agi.email, msg,  df, requireTransportSecurity=False,requireAuthentication=True)
        reactor.connectTCP(mailhost, mailport, f)

    def onHangup(self,option):
        """Cause the server to hang up on the channel
        Returns deferred integer response code
        """
        s = fastagi.InSequence()
        s.append(self.agi.hangup)
        s()

dbpool = None
host = config.get("db", "host")
db = config.get("db", "db")
user = config.get("db", "user")
passwd = config.get("db","passwd")

def onConnect(*args):
    log.debug("Connected to DB ")

def connectDB(cb):
    """Create a new ConnectionPool.

        Any positional or keyword arguments other than those documented here
        are passed to the DB-API object when connecting. Use these arguments to
        pass database names, usernames, passwords, etc.

        cp_noisy: generate informational log messages during operation

        cp_openfun: a callback invoked after every connect() on the
                           underlying DB-API object. The callback is passed a
                           new DB-API connection object.  This callback can
                           setup per-connection state such as charset,
                           timezone, etc.

        cp_reconnect: detect connections which have failed and reconnect
                             (default False). Failed connections may result in
                             ConnectionLost exceptions, which indicate the
                             query may need to be re-sent.
        """
    global dbpool
    dbpool = adbapi.ConnectionPool('MySQLdb',
                                   host=host,
                                   db=db,
                                   user=user,
                                   passwd = passwd,
                                   cursorclass = MySQLdb.cursors.DictCursor,
                                   cp_reconnect=True,
                                   cp_openfun=cb,
                                   cp_noisy=True)

connectDB(onConnect)

logpath = config.get("paths", "log")
rootlogger = logging.getLogger('')
fmt = logging.Formatter('%(asctime)s-%(name)s-%(levelname)s : %(message)s')
sh = logging.StreamHandler()
sh.setFormatter(fmt)
rootlogger.addHandler(sh)
rfh = logging.handlers.RotatingFileHandler(logpath+"lvm.log", maxBytes=50000, backupCount=5)
rfh.setFormatter(fmt)
rootlogger.addHandler(rfh)


def route(agi):
    Lecture(agi)


application = getApp("Lecture", route)
                                                                      


