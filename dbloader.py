#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re, commands, datetime, sys, os, time, codecs
from time import gmtime, strftime, localtime
import MySQLdb
from xml.sax import make_parser
from xml.sax.handler import ContentHandler

addTagQueue = {}
addReferenceQueue = {}

refdict = {}

titles = {}
if os.environ['HOME'].startswith('/home'):
    PATHPREFIX = '/home/ec2-user/hepsoftware'
else:
    PATHPREFIX = '/Users/wenaus/Dropbox/BNL/hepsoftware/django/hepsoftware'

people_dict = {}
entity_dict = {}

debug = False
implicitTags = []

## schema
objectnames = ( 'org', 'project', 'facility', 'meeting', 'doc', 'tool', 'package', 'intro', 'people', 'task', 'concept', 'definition', 'content', 'need', 'presentation' )
singletonnames = ( 'people', )
elementnames = ( 'name', 'uses', 'tags', 'description', 'web', 'email', 'contact', 'wikipedia', 'date', 'type', 'phonebook', 'credit', 'docref', 'repo', 'paper', 'talk', 'image', 'logo', 'location', 'contributor', 'status' )
ignorenames = ( 'comment', 'a', 'notes', 'hepsoftware', )

## set up DB
MySQLdb.charset = 'utf8'
dbpassfile = '%s/../hepsoftwaredbpass' % PATHPREFIX
if not os.path.exists(dbpassfile):
    print "Password file not found."
    sys.exit()
dbpass = commands.getoutput('cat %s' % dbpassfile)
dbhandle = MySQLdb.connect(host='localhost',db='hepsoftware',user='hepsoftware',passwd=dbpass,use_unicode=True,charset='utf8')
dictcursor = dbhandle.cursor(cursorclass=MySQLdb.cursors.DictCursor)
dictcursor.execute('SET FOREIGN_KEY_CHECKS=1;')
dictcursor.execute('SET NAMES UTF8;')

for table in ( 'tag', 'entity', 'reference' ):
    query = u'select count(*) from hepsoftware_%s' % table
    dictcursor.execute(query)
    rows = dictcursor.fetchall()
    count = rows[0]['count(*)']
    if debug: print '%s count: %s' % ( table, count )

dictcursor.execute("delete from hepsoftware_entity")
dictcursor.execute("delete from hepsoftware_tag")
dictcursor.execute("delete from hepsoftware_reference")

tnow = datetime.datetime.now()
objectlist = []

class myHandler(ContentHandler):
    object = {}  # current object being worked with
    inobject = False
    def startElement(self, nm, attrs):
        self.token = nm
        self.content = ''
        if nm in objectnames:
            ## Starting a new object.
            self.object = {}
            self.object['objectname'] = nm
            self.object['elements'] = []
            self.object['source'] = ""
            self.inobject = True
        elif nm in elementnames:
            pass
        elif nm in ignorenames:
            pass
        else:
            print "Unknown tag", nm
        
    def endElement(self, nm):
        if nm in ignorenames: return
        #print self.content
        if not self.inobject: print "At end of element but not in an object:", self.object, self.token, self.content

        if nm in elementnames:
            ## Add the element to object and continue
            #print "Setting %s.%s to value: %s" % ( self.object['objectname'], self.token, self.content )
            if self.content.strip() != '':
                self.object[self.token.lower().strip()] = self.content.strip()
                try:
                    self.object['elements'].append( { self.token.lower().strip() : self.content.strip() } )
                except:
                    print "Fail in ", self.object
            return
 
        if nm in objectnames:
            ## Closing an object.
            self.inobject = False
            objectlist.append(self.object)
            self.object = {}
        else:
            print "Unknown tag", nm

    def characters(self, chars):
        #chars = chars.replace(u'\n','<br>')
        self.content += unicode(chars)

    def endDocument(self):
        pass

xh = myHandler()
parser = make_parser()
parser.setContentHandler(xh)

fdir = PATHPREFIX
tmpname = '/tmp/hepsoftware-autogen.xml'
fname = []
fname.append('%s/hepsoftware-db.xml' % fdir)

for cf in fname:
    fh = codecs.open(cf,'r','utf-8')
    fo = codecs.open(tmpname,'w','utf-8')
    lines = fh.readlines()
    for l in lines:
        lout = l.replace('&','&amp;')
        fo.write(lout)
    fo.close()
    fh.close()

    fh = open(tmpname,'r')
    print "Parsing %s... use xmllint if parsing errors are encountered" % fname
    parser.parse(fh)    
    fh.close()
    ## Again, once all the entities and references are known. So that #tagrefs in descriptions are properly expanded.
    fh = open(tmpname,'r')
    parser.parse(fh)    
    fh.close()

## Process the acquired content

def getImplicitTags(tag):
    tret = []
    for t in implicitTags:
        tfrom, tto = t
        if tag in tfrom:
            for tt in tto:
                tret.append(tt)
    dret = {}
    for t in tret:
        dret[t] = 1
    tret = dret.keys()
    tret.sort()
    tstr = ""
    for t in tret:
        tstr += " %s " % t  
    return tret, tstr

def saveTags(obj, addtags=''):
    if not 'tags' in obj: return '%s_%s' % ( obj['objectname'], obj['name']), None, None
    savetag = ''
    taglist = []
    addtagl = addtags.split(',')
    for t in addtagl:
        taglist.append([t.strip(),''])
    alltags = ""
    allmytags = ""
    taglines = obj['tags'].split('\n')
    for t1 in taglines:
        if t1.find('|') >= 0:
            tag = t1.split('|')
            tagl = [ tag[0].strip(), tag[1].strip() ]
            taglist.append(tagl)
        else:
            t2 = t1.split(' ')
            for t in t2:
                taglist.append([t.strip(), ''])
    mastertag = False
    for tagl in taglist:
        tagowner = False
        tag, desc = tagl
        if tag == '': continue
        if tag.startswith('*') and not mastertag:
            ## the first appearing owned tag (prefixed by *) is the reference tag of the entity.
            tagname = tag[1:]
            mastertag = True
            tagowner = True
            savetag = tagname
            allmytags += " %s " % tagname
            alltags += " %s " % tagname
        elif tag.startswith('*'):
            ## another owned tag
            tagname = tag[1:]
            tagowner = True
            allmytags += " %s " % tagname
            alltags += " %s " % tagname
        elif tag.endswith('*'):
            ## endswith * indicates 'usedby'. Don't add it as a tag, use a reference.
            tagname = tag[:-1]
            addReference(savetag, 'usedby', textref='', description=desc, tagref=tagname)
        else:
            tagname = tag
            alltags += " %s " % tagname

        implicitl, implicitt = getImplicitTags(tagname)
        alltags += " %s " % implicitt

        allmytagl = allmytags.split()
        allmytagd = {}
        for t in allmytagl:
            allmytagd[t.strip()] = 1
        allmytagl = allmytagd.keys()
        allmytagl = sorted(allmytagl, key=lambda x:x.lower())
        allmytags = ''
        for t in allmytagl:
            allmytags += " %s " % t
        alltagl = alltags.split()
        alltagd = {}
        for t in alltagl:
            alltagd[t.strip()] = 1
        alltagl = alltagd.keys()
        alltagl = sorted(alltagl, key=lambda x:x.lower())
        alltags = ''
        for t in alltagl:
            alltags += " %s " % t

        entity = obj['name']
        if 'type' in obj:
            type = obj['type']
        else:
            type = 'tag'
        if 'subtype' in obj:
            subtype = obj['subtype']
        else:
            subtype = ''
        if tagowner:
            implicitl, implicitt = getImplicitTags(tagname)
            query = u'insert into hepsoftware_tag (name,type,subtype,description,implicit,created_at,updated_at) values ("%s","%s","%s","%s","%s","%s","%s") on duplicate key update type="%s", subtype="%s", description="%s", implicit="%s", updated_at="%s"' % ( tagname, type, subtype, desc, implicitt, tnow, tnow, type, subtype, desc, implicitt, tnow )
            if debug: print 'savetags owner', query
            dictcursor.execute(query)
        else:
            implicitl, implicitt = getImplicitTags(tagname)
            query = u'insert into hepsoftware_tag (name, implicit, created_at, updated_at) values ("%s","%s","%s","%s") on duplicate key update implicit="%s", updated_at="%s"' % ( tagname, implicitt, tnow, tnow, implicitt, tnow )
            if debug: print 'savetags not owner', query
            dictcursor.execute(query)
            tagl, tagt = getImplicitTags(tagname)
            for t in tagl:
                implicitl, implicitt = getImplicitTags(t)
                query = u'insert into hepsoftware_tag (name, implicit, created_at, updated_at) values ("%s","%s","%s","%s") on duplicate key update implicit="%s", updated_at="%s"' % ( t, implicitt, tnow, tnow, implicitt, tnow )
                if debug: print query
                dictcursor.execute(query)

    if mastertag:
        return savetag, allmytags, alltags
    else:
        return None, allmytags, alltags

def saveEntity(obj, owntag, type=None, allmytags='', alltags=''):
    name = obj['name']
    titles[owntag] = name
    if type:
        obj['type'] = type
    elif 'type' in obj:
        type = obj['type']
    else:
        type = ''
    if 'subtype' in obj:
        subtype = obj['subtype']
    else:
        subtype = ''
    if 'description' in obj:
        desc = cleanText(obj['description'], owntag)
        desc_original = cleanMinimalText(obj['description'])
    else:
        desc = u''
        desc_original = u''
    if 'type' in obj and obj['type'] == 'meeting':
        #print '>>>> meeting', obj['name'], obj['location'], obj['date']
        date = datetime.datetime.strptime(obj['date'], '%Y-%m-%d')
        if 'location' in obj:
            location = expandText(obj['location'], owntag, 'location')
        else:
            location = ''
    else:
        date = tnow.strftime('%Y-%m-%d')
        location = ''

    desc8 = unicode(desc)
    desc_html8 = unicode(desc_original)
    entity_dict[owntag] = 1
    query = u'insert into hepsoftware_entity (mytag,date,name,type,subtype,description,description_markup,location,allmytags,alltags,created_at,updated_at) values ("%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s","%s") on duplicate key update date="%s", name="%s", type="%s", subtype="%s", description="%s", description_markup="%s", location="%s", allmytags="%s", alltags="%s", updated_at="%s"' % ( owntag, date, name, type, subtype, desc8, desc_html8, location, allmytags, alltags, tnow, tnow, date, name, type, subtype, desc8, desc_html8, location, allmytags, alltags, tnow )
    if debug: print query
    dictcursor.execute(query)

    ## add references etc. which may have multiple element instances
    if 'elements' in obj:
        for el in obj['elements']:
            desc = ''
            if 'wikipedia' in el:
                ref = el['wikipedia']
                desc = "http://en.wikipedia.org/wiki/%s" % el['wikipedia']
                addReference(owntag, 'wikipedia', ref, desc)
            for token in ( 'web', 'paper', 'talk', 'contact', 'contributor', 'credit', 'date', 'repo', 'docref', 'uses', 'image', 'logo', 'phonebook', 'status', 'location'):
                tag_original = ''
                if token in el:
                    wls = el[token].split('\n')
                    for wl in wls:
                        wt = wl.split('|')
                        ref = wt[0].strip()
                        if token not in ['uses', ]: desc = token
                        if token in [ 'web', ]: desc = ''
                        if len(wt) > 1: desc = wt[1].strip()
                        if token in ( 'contact', 'contributor', 'credit' ):
                            refl = re.split(',',ref)
                        elif token in ( 'status', 'location'):
                            tag_original = ref
                            refl = ( ref, )
                        elif token == 'docref':
                            refl = (ref, )
                        else:
                            refl = re.split(' |,',ref)
                        for r in refl:
                            tagref = ''
                            if token in ( 'contact', 'contributor', 'credit' ):
                                desc = token
                                tagref = r.strip().lower().replace(' ','_')
                                people_dict[tagref] = 'ref'
                            elif token in ( 'uses', ):
                                tagref = r
                                addReference(tagref, 'usedby', owntag, desc, owntag)
                            addReference(owntag, token, r, desc, tagref)
                            if token == 'uses':
                                implicitl, implicitt = getImplicitTags(r)
                                query = u'insert into hepsoftware_tag (name, implicit, created_at, updated_at) values ("%s","%s","%s","%s") on duplicate key update implicit="%s", updated_at="%s"' % ( r, implicitt, tnow, tnow, implicitt, tnow )
                                if debug: print query
                                dictcursor.execute(query)

def addReference(entity, type, textref, description='', tagref=''):
   global addReferenceQueue
   tok = "%s____%s____%s____%s" % ( entity, type, textref, tagref )
   addReferenceQueue[ tok ] = description

def addAllReferences():
    for q in addReferenceQueue:
        entity, type, textref, tagref = q.split('____')
        description = addReferenceQueue[q]
        addReferenceExe(entity, type, textref, description=description, tagref=tagref)

def addReferenceExe(entity, type, textref, description='', tagref=''):
        tok = "%s__%s__%s__%s" % ( entity, type, textref, tagref )
        #if tok not in refdict:
        #    refdict[tok] = 1
        #    return
        description = expandText(description, entity, type=type)
        textref8 = unicode(textref)
        description8 = unicode(description)
        query = u'insert into hepsoftware_reference (entity,type,textref,tagref,description,created_at,updated_at) values ("%s","%s","%s","%s","%s","%s","%s") on duplicate key update type="%s", textref="%s", tagref="%s", description="%s", updated_at="%s"' % ( entity, type, textref8, tagref, description8, tnow, tnow, type, textref8, tagref, description8, tnow )
        if debug: print query
        dictcursor.execute(query)
        #if type == 'contact':
        #    ## add the contact as a tag on the entity
        #    addTag(entity, textref.strip().lower().replace(' ','_'))

def addTag(entity, addtag):
   global addTagQueue
   addTagQueue[ "%s____%s" % ( entity.strip(), addtag.strip(), ) ] = 1

def addAllTags():
    for q in addTagQueue:
        entity, addtag = q.split('____')
        addTagExe(entity, addtag)

def addTagExe(entity, addtag):
    query = u'select alltags from hepsoftware_entity where mytag="%s"' % entity
    if debug: print query
    dictcursor.execute(query)
    rows = dictcursor.fetchall()
    if len(rows) > 0:
        alltags = rows[0]['alltags']
        alltags += "%s " % addtag
        tagd = {}
        for tag in alltags.split():
            tagd[tag.strip()] = 1
        newtagl = tagd.keys()
        newtagl.sort()
        newalltags = ''
        for tag in newtagl:
            newalltags += " %s " % tag
        query = u'update hepsoftware_entity set alltags="%s" where mytag="%s"' % ( newalltags, entity )
        if debug: print query
        dictcursor.execute(query)

def cleanMinimalText(txt):
    txt = txt.replace(u'"',u'\\"')
    return txt

def expandText(txt, owntag, type='', description=''):
    ## Set up #hashlinks
    pat = re.compile('\#([a-zA-Z0-9\-\_]+)')
    for i in range (0,50):
        mat = pat.search(txt)
        if mat:
            tagname = mat.group(1).lower()
            if tagname in titles:
                title = titles[tagname]
            else:
                title = mat.group(1)
            taglink = '<a href="/e/%s">%s</a>' % ( tagname, title )
            txt = txt.replace(mat.group(0),taglink)
            if type in ( 'location', ):
                ## add tag to the associated meeting    
                addTag(owntag, tagname)
            if type in ( 'talk', 'paper', ):
                ## add reference to the talk/paper to the associated meeting 
                addReferenceExe(tagname, type, '', description=txt, tagref=owntag)
        else:
            break
    txt = txt.replace(u'"',u'\\"')
    txt = txt.replace(u'[[hash]]',u'#')
    return txt

def cleanText(txt, owntag):
    ## Set up images
    pat = re.compile('.*(__img_)([\s]*)([^(\s|\n|<)]+)')
    for i in range (0,10):
        mat = pat.search(txt)
        imgurl = ''
        if mat:
            imgurl = mat.group(3)
            if imgurl.find('.') < 0: imgurl += '.png'
            fullurl = "/static/img/%s" % imgurl
            markup = "![](%s)" % fullurl
            txt = txt.replace(mat.group(0),markup)
            print "IMAGE: replacing %s with %s" % ( mat.group(0), markup )
            ## add an image reference
            addReference(owntag, 'image_inline', textref=fullurl)
        else:
            break

    tmpfile = "/tmp/desc.txt"
    tmpfilein = "/tmp/desc.html"
    fo = codecs.open(tmpfile,'w','utf-8')
    fo.write(txt)
    fo.close()
    markdown = "perl %s/Markdown.pl --html4tags %s > /tmp/desc.html" % ( PATHPREFIX, tmpfile)
    outtxt = commands.getoutput(markdown)
    fi = codecs.open(tmpfilein,'r','utf-8')
    outtxt = fi.read()
    fi.close()
    outtxt = expandText(outtxt, owntag)
    return outtxt

def proc_org(obj, type='org',addtags=''):
    if debug: print 'savetags org'
    owntag, allmytags, alltags = saveTags(obj, addtags)
    if owntag:
        saveEntity(obj, owntag, type, allmytags, alltags)
    else:
        print '****** Needs a tag it owns:', obj

def proc_tool(obj):
    proc_org(obj, type='tool', addtags='software')

def proc_project(obj):
    proc_org(obj, type='project', addtags='software')

def proc_meeting(obj):
    proc_org(obj, type='meeting')

def proc_task(obj):
    proc_org(obj, type='task')

def proc_definition(obj):
    proc_org(obj, type='definition')

def proc_presentation(obj):
    proc_org(obj, type='presentation')

def proc_content(obj):
    if obj['name'] == 'tagtree':
        proc_tagtree(obj)
    else:
        proc_org(obj, type='content')

def proc_people(obj):
    type = 'person'
    plist = obj['description']
    plist = plist.split('\n')
    for p in plist:
        parts = p.split('|')
        name = parts[0].strip()
        nametag = name.lower().replace(' ','_')
        titles[nametag] = name
        tagstring = ' *%s ' % nametag
        othertagstring = ''
        email = ''
        desc = ''
        tags = []
        if len(parts) > 0:
            tokens = parts[1].split()        
            for t in tokens:
                if t.find('@') >= 0:
                    email = t
                else:
                    tags.append(t)
                    tagstring += ' %s ' % t
                    othertagstring += ' %s ' % t
            if len(parts) > 2: desc = parts[2]

        ## save a tag for the person
        _tag = 'person'
        subtype = ''
        query = u'insert into hepsoftware_tag (name,type,subtype,description,created_at,updated_at) values ("%s","%s","%s","%s","%s","%s") on duplicate key update type="%s", subtype="%s", description="%s", updated_at="%s"' % ( nametag, type, subtype, name, tnow, tnow, type, subtype, name, tnow )
        if debug: print query
        dictcursor.execute(query)

        pobj = {}
        #pobj['tags'] = othertagstring
        pobj['tags'] = tagstring
        pobj['name'] = name
        pobj['description'] = name
        if debug: print 'savetags people'
        entity_dict[nametag] = 1
        owntag, allmytags, alltags = saveTags(pobj)
        query = u'insert into hepsoftware_entity (mytag,name,type,subtype,description,allmytags,alltags,created_at,updated_at) values ("%s","%s","%s","%s","%s","%s","%s","%s", "%s") on duplicate key update name="%s", type="%s", subtype="%s", description="%s", allmytags="%s", alltags="%s", updated_at="%s"' % ( nametag, name, type, subtype, desc, allmytags, alltags, tnow, tnow, name, type, subtype, desc, allmytags, alltags, tnow )
        if debug: print query
        dictcursor.execute(query)

        ## Create reference for email
        if email != '': addReference(nametag, 'email', email, description='', tagref='')       

def proc_tagtree(obj):
    global implicitTags
    ttlist = obj['description']
    ttlist = ttlist.split('\n')
    for tt in ttlist:
        parts = tt.split('=')
        if len(parts) > 1:
            fromtags = parts[0].split()
            totags = parts[1].split()
            implicitTags.append( [ fromtags, totags ] )
        else:
            print "Bad tagtree:", tt

for obj in objectlist:
    if 'objectname' not in obj:
        print '*** Missing objectname', obj
        continue
    if 'name' not in obj and obj['objectname'] not in singletonnames:
        print 'no name:', obj
        continue
    if obj['objectname'] in objectnames:
        ## Call the object processor proc_<objectname>, if existing
        procname = 'proc_%s' % obj['objectname']
        if procname in  globals():
            globals()[procname](obj)
        else:
            print "Cannot process", obj['objectname']

addAllTags()
addAllReferences()

for table in ( 'tag', 'entity', 'reference' ):
    query = u'select count(*) from hepsoftware_%s' % table
    if debug: print query
    dictcursor.execute(query)
    rows = dictcursor.fetchall()
    count = rows[0]['count(*)']
    print '%s count: %s' % ( table, count )

if debug: print query
dictcursor.execute("flush tables")

for p in people_dict:
    if p not in entity_dict:
        print "Missing person: ", p

