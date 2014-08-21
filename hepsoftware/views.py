# -*- coding: utf-8 -*-
import os, re, codecs, commands, glob
from datetime import datetime, timedelta
import json
from pprint import pprint
import autocomplete_light

from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.db.models import Q
from django.shortcuts import render_to_response, render
from django.template import RequestContext, loader
from django.db.models import Count
from django import forms
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from django import forms
from django.forms import extras
from django.contrib import messages

#from jinja2 import Template

from models import Entity
from models import Tag
from models import Reference

if os.environ['HOME'].startswith('/home'):
    PATHPREFIX = '/home/ec2-user/hepsoftware'
    ARCHIVE_DIR = '/home/ec2-user/hepsoftware/archive'
else:
    PATHPREFIX = '/Users/wenaus/Dropbox/BNL/hepsoftware/django/hepsoftware'
    ARCHIVE_DIR = '/Users/wenaus/Dropbox/BNL/hepsoftware/django/hepsoftware/archive'

QUERY_TYPE = ''

PERSONS = []
PERSONS_DICT = {}
people = Entity.objects.filter(type='person').values('name','mytag').order_by('name')
for p in people:
    PERSONS.append(p['name'])
    PERSONS_DICT[p['mytag']] = p['name']

AUTOCOMPLETE_ENTITIES = []
autoents = Entity.objects.exclude(type__in=('meeting','person','doc','paper','presentation','content',)).values('mytag').order_by('mytag')
for e in autoents:
    AUTOCOMPLETE_ENTITIES.append(e['mytag'])

ENTITY_CHOICES = [ 'Project', 'Tool', 'Organization', 'Person', 'Meeting', 'Document', 'Task', 'Definition', ]

def classifyQuery(request, tag='', type='', subtype=''):
    global QUERY_TYPE
    if 'type' in request.GET:
        if request.GET['type'] in  [ 'person', 'meeting', 'project', 'tool', 'definition', ]:
            QUERY_TYPE = request.GET['type']
            return
        if request.GET['type'] == 'org' and 'tag' not in request.GET:
            QUERY_TYPE = 'org'
            return
    taglist = [ 'meeting', 'experiment', 'lab', 'university', 'software', 'analysis', 'provider', ]
    if 'querytype' in request.GET:
        QUERY_TYPE = request.GET['querytype']
    elif tag in taglist:
        QUERY_TYPE = tag
    else:
        if tag != '': QUERY_TYPE = tag
        elif type != '': QUERY_TYPE = type
        else: QUERY_TYPE = ''

def getEntities(request, query, orderby='name', tagname=''):
    QUERY_TYPE = ''
    classifyQuery(request)
    dbquery = Entity.objects
    if query: dbquery = dbquery.filter(**query)
    params = request.GET.copy()
    if tagname != '': params['tag'] = tagname
    for param in params:
        if param == 'tag':
            val = params[param].lower().strip()
            if val.find('|') >= 0:
                ## or
                criterion = False
                tags = val.split('|')
                for t in tags:
                    t = " %s " % t.strip()
                    classifyQuery(request,tag=t)
                    if criterion == False:
                        criterion = Q(alltags__icontains=t)
                    else:
                        criterion = criterion | Q(alltags__icontains=t)
                dbquery = dbquery.filter(criterion)
            elif val.find('^') >= 0:
                ## and
                tags = val.split('^')
                for t in tags:
                    t = " %s " % t.strip()
                    dbquery = dbquery.filter(alltags__contains=t)
            else:
                classifyQuery(request,tag=val)
                dbquery = dbquery.filter(alltags__contains=" %s " % val)
        elif param == 'xtag':
            dbquery = dbquery.filter(alltags__exclude=" %s " % val)
        elif param == 'type':
            dbquery = dbquery.filter(type=params[param])
        elif param == 'subtype':
            dbquery = dbquery.filter(subtype=params[param])
    ents = dbquery.order_by(orderby).values()
    return ents

def mainPage(request):
    content = Entity.objects.filter(type='content',name='intro').values()

    if 'archive' in request.GET and request.user.is_authenticated():
        archive(request)

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'description' : content[0]['description'],
            'user' : request.user,
            'loggedin' : request.user.is_authenticated(),
        }
        return render_to_response('hepsoftwareMain.html', data, RequestContext(request))

def userContribs(request, username=''):
    user = request.user
    requestParams = request.GET.copy()
    requestParams['type'] = 'contributions'
    usertag = "%s_%s" % ( user.first_name.lower(), user.last_name.lower() )
    return entityInfo(request, usertag)
    query = {}
    query['tagref'] = usertag
    refs = Reference.objects.filter(**query).order_by('entity').values()
    entnames = Entity.objects.filter().values('name','mytag')
    for ref in refs:
        for ent in entnames:
            if ent['mytag'] == ref['entity']:
                ref['name'] = ent['name']
                break

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'requestParams' : requestParams,
            'user' : request.user,
            'usertag' : usertag,
            'loggedin' : request.user.is_authenticated(),
            'refs': refs,
        }
        return render_to_response('referList.html', data, RequestContext(request))

def entityList(request, tagname=''):
    query = {}
    if 'tag' in request.GET: tagname= request.GET['tag']
    ents = getEntities(request, query, tagname=tagname)
    ents = sorted(ents, key=lambda x:x['name'].lower())
    title = titletag = ""
    if tagname != '': title = tagname
    for ent in ents:
        if tagname == ent['mytag']:
            title = ent['name']
            titletag = request.GET['tag']
        alltagl = ent['alltags'].split()
        mytagl = ent['allmytags'].split()
        othertagl = []
        for t in alltagl:
            if t not in mytagl: othertagl.append(t)
        ent['mytagl'] = mytagl
        ent['othertagl'] = othertagl

    usedby = []
    ## entities that use this
    if tagname != '':
        usedby = Reference.objects.filter(type='uses').filter(tagref=tagname).order_by('entity').values()
        for u in usedby:
            # convert from uses to usedby
            user = u['entity']
            usee = u['tagref']
            u['entity'] = usee
            u['tagref'] = user
            u['type'] = 'usedby'
        ## Clean out duplicates
        usedbyd = {}
        usedby2 = []
        for ub in usedby:
            if ub['tagref'] in usedbyd: continue
            usedbyd[ub['tagref']] = 1
            usedby2.append(ub)
        usedby = sorted(usedby2, key=lambda x:x['tagref'])

    ## get entity names
    ubl = []
    for ub in usedby:
        ubl.append(ub['tagref'])
    usedbyent = Entity.objects.filter(mytag__in=ubl).values('name','mytag')
    for e in usedbyent:
        for ub in usedby:
            if ub['tagref'] == e['mytag']: ub['name'] = e['name']
    for u in usedby:
        if 'name' not in u: u['name'] = u['tagref']

    eorg, esw, epeople, eother, emeet = entityGroups(ents, tagname)

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'requestParams' : request.GET,
            'user' : request.user,
            'loggedin' : request.user.is_authenticated(),
            'tagname' : tagname,
            'ents': ents,
            'usedby' : usedby,
            'eorg' : eorg,
            'esw' : esw,
            'epeople' : epeople,
            'eother' : eother,
            'emeet' : emeet,
            'QUERY_TYPE' : QUERY_TYPE,
            'title' : title,
            'titletag' : titletag,
        }
        return render_to_response('entityList.html', data, RequestContext(request))

def tagLists(ent):
    try:
        allmytagl = ent['allmytags'].split()
        allmytagl.sort()
    except:
        allmytagl = []
    try:
        alltags = ent['alltags']
        for tag in allmytagl:
            alltags = alltags.replace(" %s " % tag, " ")
        alltagl = alltags.split()
        alltagl.sort()
    except:
        alltagl = []
    return allmytagl, alltagl

def entityGroups(ents, tagname):
    eorg = []
    esw = []
    epeople = []
    eother = []
    emeet = []
    for e in ents:
        if e['mytag'] == tagname: continue
        if e['type'] == 'meeting':
            emeet.append(e)
        elif e['type'] == 'person':
            epeople.append(e)
        elif e['type'] == 'org':
            eorg.append(e)
        elif (e['type'] in ['project', 'tool', 'package', 'service']) or e['alltags'].find(' software ') >= 0:
            esw.append(e)
        else:
            eother.append(e)
    emeet = sorted(emeet, key=lambda x:x['date'], reverse=True)
    return eorg, esw, epeople, eother, emeet

def archive(request):
    ents = Entity.objects.values('mytag')
    for e in ents:
        entityInfo(request, e['mytag'], save_to_json=True)
    messages.info(request, "All entries archived.")

def entityInfo(request, name=None, save_to_json=False, save_to_db=False):
    if name:
        tagname = name
    elif 'name' in request.GET:
        tagname = request.GET['name']
    elif 'tag' in request.GET:
        tagname = request.GET['tag']
    else:
        tagname = ''
    contributor = ''
    credit = ''
    if 'save_to_json' in request.GET:
        save_to_json = True
    if 'save_to_db' in request.GET:
        save_to_db = True
    ents = Entity.objects.filter(mytag=tagname).values()
    ent = mytags = tags = tagents = refs = None
    othertags = []
    notmytags = []
    if len(ents) > 0:
        ent = ents[0]
        mytags, tags = tagLists(ent)
        ## tagged entities
        tagents = Entity.objects.filter(mytag__in=tags).values('mytag','name')
        othertags = tags[:]
        for e in tagents:
            othertags.remove(e['mytag'])
        if 'description' in ent: ent['description'] = ent['description'].strip()
    else:
        return entityList(request, tagname)

    ## get the revision history
    path = ARCHIVE_DIR + '/' + tagname
    mtime = lambda f: os.stat(os.path.join(path, f)).st_mtime
    try:
        revisionfiles = list(sorted(os.listdir(path), key=mtime, reverse=True))
    except:
        revisionfiles = []

    ## get references to this entity
    refo = Reference.objects.filter(entity=tagname).values()
    refo = sorted(refo, key=lambda x:x['description'].lower())
    refo = sorted(refo, key=lambda x:x['type'].lower())
    usedby = []
    uses = []
    refs = []
    image = {}
    logo = ''
    for ref in refo:
        ## Set up #hashlinks
        pat = re.compile('\#([a-zA-Z0-9\-\_]+)')
        for i in range (0,30):
            mat = pat.search(ref['tagref'])
            if mat:
                tname = mat.group(1).lower()
                tage = Entity.objects.filter(mytag=tname).values()
                if len(tage) > 0:
                    title = tage[0]['name']
                else:
                    tagt = Tag.objects.filter(name=tagname).values()
                    if len(tagt) > 0:
                        title = tagt[0]['name']
                    else:
                        title = tagname
                taglink = '<a href="/e/%s">%s</a>' % ( tagname, title )
                ref['tagref'] = ref['tagtref'].replace(mat.group(0),taglink)
                ref['textref'] = ref['tagref']
            else:
                break

        if ref['type'] == 'usedby':
            usedby.append(ref)
        elif ref['type'] == 'uses':
            uses.append(ref)
        elif ref['type'] == 'image':
            image['url'] = ref['textref']
            image['desc'] = ref['description']
        elif ref['type'] == 'logo':
            logo = ref['textref']
        elif ref['type'] == 'contributor':
            newcontributor = ref['tagref']
            newcontributorname = ref['textref']
            contributor += "<a href='/e/%s'>%s</a> &nbsp; " % ( newcontributor, newcontributorname )
        elif ref['type'] == 'credit':
            newcredit = ref['tagref']
            newcreditname = ref['textref']
            credit += "<a href='/e/%s'>%s</a> &nbsp; " % ( newcredit, newcreditname )
        else:
            refs.append(ref)

    ## get references to this
    refstothiso = Reference.objects.exclude(type='uses').exclude(type='usedby').filter(tagref=tagname).order_by('entity').values()
    refstothis = []
    for r in refstothis:
        refstothis.append(r)

    ## entities that are used by this
    usedbythis = Reference.objects.filter(type='usedby').filter(tagref=tagname).order_by('entity').values()
    for u in usedbythis:
        # convert from uses to usedby
        user = u['entity']
        usee = u['tagref']
        u['entity'] = usee
        u['tagref'] = user
        u['type'] = 'uses'
        uses.append(u)
    ## Clean out duplicates
    usesd = {}
    uses2 = []
    for u in uses:
        if u['tagref'] in usesd: continue
        usesd[u['tagref']] = 1
        uses2.append(u)
    uses = sorted(uses2, key=lambda x:x['tagref'])

    ## entities that use this. Add to usedby
    usedbytoo = Reference.objects.filter(type='uses').filter(tagref=tagname).order_by('entity').values()
    for u in usedbytoo:
        # convert from uses to usedby
        user = u['entity']
        usee = u['tagref']
        u['entity'] = usee
        u['tagref'] = user
        u['type'] = 'usedby'
    usedby += usedbytoo
    ## Clean out duplicates
    usedbyd = {}
    usedby2 = []
    for ub in usedby:
        if ub['tagref'] in usedbyd: continue
        usedbyd[ub['tagref']] = 1
        usedby2.append(ub)
    usedby = sorted(usedby2, key=lambda x:x['tagref'])

    ## get entity names
    ubl = []
    for ub in usedby:
        ubl.append(ub['tagref'])
    for ub in uses:
        ubl.append(ub['tagref'])
    for ub in refstothis:
        ubl.append(ub['entity'])
    usedbyent = Entity.objects.filter(mytag__in=ubl).values('name','mytag')
    for e in usedbyent:
        for ub in usedby:
            if ub['tagref'] == e['mytag']: ub['name'] = e['name']
        for u in uses:
            if u['tagref'] == e['mytag']: u['name'] = e['name']
        for u in refstothis:
            if u['entity'] == e['mytag']: u['name'] = e['name']

    for u in uses:
        if 'name' not in u: u['name'] = u['tagref']
    for u in refstothis:
        if 'name' not in u: u['name'] = u['tagref']

    ## get entities with this tag
    entswith = Entity.objects.filter(alltags__contains=' %s ' % tagname).values('mytag','allmytags','alltags','name','type','date')
    entswith = sorted(entswith, key=lambda x:x['name'].lower())
    for e in entswith:
        for p in request.GET:
            if p == 'tag' and request.GET[p] == e['mytag']:
                title = tagname
        alltagl = e['alltags'].split()
        mytagl = e['allmytags'].split()
        othertagl = []
        for t in alltagl:
            if t not in mytagl: othertagl.append(t)
        e['mytagl'] = mytagl
        e['othertagl'] = othertagl

    eorg, esw, epeople, eother, emeet = entityGroups(entswith, tagname)

    ## are we looking at a particular revision?
    if 'rev' in request.GET:
        revisionfile = "%s/%s/%s" % ( ARCHIVE_DIR, tagname, request.GET['rev'] )
        fh = codecs.open(revisionfile,'r','utf-8')
        jsondata = json.load(fh)
        fh.close()
        ent = jsondata['ent']
        mytags = jsondata['mytags']
        othertags = jsondata['othertags']
        refs = jsondata['refs']
        refstothis = jsondata['refstothis']
        usedby = jsondata['usedby']
        uses = jsondata['uses']
        image = jsondata['image']
        logo = jsondata['logo']
    else:
        jsondata = {
            'user' : request.user.username,
            'loggedin' : request.user.is_authenticated(),
            'tagname' : tagname,
            'ent': ent,
            'mytags' : mytags,
            'tags' : tags,
            'othertags' : othertags,
            # other refs besides uses, usedby, image etc.
            'refs' : refs,
            'refstothis' : refstothis,
            'usedby' : usedby,
            'uses' : uses,
            'image' : image,
            'logo' : logo,
        }

    ## are we supposed to save this?
    if save_to_db and tagname != '':
        save_to_json = True
        saveEntity(request, ent)
    if save_to_json and tagname != '':
        revisionfiledir = "%s/%s" % ( ARCHIVE_DIR, tagname )
        if not os.path.isdir(revisionfiledir): commands.getoutput("mkdir %s" % revisionfiledir)
        datestr = datetime.now().replace(tzinfo=None).strftime('%Y-%m-%d-%H')
        revisionfile = "%s/%s_updated_by_%s_at_%s" % ( revisionfiledir, tagname, request.user.username, datestr )
        ## Any changes since the newest?
        same = False
        try:
            newest = max(glob.iglob('%s/*' % revisionfiledir), key=os.path.getctime)
        except:
            newest = None
        if newest and len(newest) > 0:
            fh = codecs.open(newest,'r','utf-8')
            try:
                json_in = json.load(fh)
            except:
                print 'failed', tagname, newest
            fh.close()
            same = compareDicts(jsondata, json_in)
        if not same:        
            fh = codecs.open(revisionfile,'w','utf-8')
            json.dump(jsondata, fh, cls=DateEncoder)
            fh.close()
            messages.info(request, "Archived as revision '%s'. <a href='/e/%s/'>See the entry</a>" % ( os.path.basename(revisionfile), tagname) )
        else:
            messages.info(request, "The latest archive revision <a href='/e/%s/?rev=%s'>%s</a> is up to date." % ( tagname, os.path.basename(newest), os.path.basename(newest) ) )

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse(json.dumps(jsondata, cls=DateEncoder), mimetype='text/html')
    else:
        pagedata = {
            'requestParams' : request.GET,
            'user' : request.user,
            'loggedin' : request.user.is_authenticated(),
            'tagname' : tagname,
            'ent': ent,
            'entname' : tagname,
            'mytags' : mytags,
            'tags' : tags,
            'othertags' : othertags,
            'ents': tagents,
            'eorg' : eorg,
            'esw' : esw,
            'epeople' : epeople,
            'eother' : eother,
            'emeet' : emeet,
            'refs' : refs,
            'refstothis' : refstothis,
            'usedby' : usedby,
            'uses' : uses,
            'image' : image,
            'logo' : logo,
            'revisionfiles' : revisionfiles,
            'contributor' : contributor,
            'credit' : credit,
        }
        return render_to_response('entityInfo.html', pagedata, RequestContext(request))

def tagList(request):
    tagsq = Tag.objects.filter().order_by('name').values()
    tags = []
    for t in tagsq:
        tags.append(t)
    entnames = Entity.objects.filter().values('mytag','name','allmytags')
    entnamed = {}
    for e in entnames:
        entnamed[e['mytag']] = e['name']
        mytags = e['allmytags'].split()
        for t in mytags:
            entnamed[t] = e['name']
    for t in tags:
        if t['name'] in entnamed: t['fullname'] = entnamed[t['name']]

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'requestParams' : request.GET,
            'user' : request.user,
            'loggedin' : request.user.is_authenticated(),
            'tags': tags,
        }
        return render_to_response('tagList.html', data, RequestContext(request))

def referList(request):
    query = {}
    for p in request.GET:
        query[p] = request.GET[p]
    tagname = None
    if 'tagref' in request.GET:
        ent = Entity.objects.filter(mytag=request.GET['tagref']).values('mytag','name')
        if ent and len(ent) > 0: tagname = ent[0]['name']
    refs = Reference.objects.filter(**query).order_by('entity').values()
    if 'type' in request.GET and request.GET['type'] == 'docref':
        refs = sorted(refs, key=lambda x:x['description']) 
    elif 'type' in request.GET and request.GET['type'] == 'status':
        refs = sorted(refs, key=lambda x:x['entity']) 
    elif 'type' in request.GET and request.GET['type'] == 'web':
        refs = sorted(refs, key=lambda x:x['entity']) 
    else:
        refs = sorted(refs, key=lambda x:x['textref']) 

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'requestParams' : request.GET,
            'user' : request.user,
            'tagname' : tagname,
            'loggedin' : request.user.is_authenticated(),
            'refs': refs,
        }
        return render_to_response('referList.html', data, RequestContext(request))

def viewSource(request, name=None):
    if name:
        tagname = name
    elif 'name' in request.GET:
        tagname = request.GET['name']
    elif 'tag' in request.GET:
        tagname = request.GET['tag']
    else:
        tagname = ''
    xmlsource = None
    entity = None
    refs = None
    usedby = ''
    uses = ''
    mytagl = []
    alltagl = []
    othertagl = []
    otherrefs = []
    if tagname == '':
        fname = '%s/hepsoftware-db.xml' % PATHPREFIX
        fh = codecs.open(fname,'r','utf-8')
        xmlsource = fh.read()
        fh.close()
    else:
        ents = Entity.objects.filter(mytag=tagname).order_by('mytag').values()
        if len(ents) > 0:
            entity = ents[0]        
            mytagl = entity['allmytags'].split()
            alltagl = entity['alltags'].split()
            othertagl = []
            for t in alltagl:
                if t not in mytagl: othertagl.append(t)
            tagstr = ""
            for t in mytagl:
                tagstr += "*%s " % t
            for t in othertagl:
                tagstr += "%s " % t
            refs = Reference.objects.filter(entity=tagname).exclude(type='image_inline').order_by('tagref').values()
            otherrefs = []
            for ref in refs:
                if ref['type'] == 'tag' and ref['entity'] == tagname: continue
                if ref['type'] == 'usedby':
                    usedby += "%s " % ref['tagref'] 
                elif ref['type'] == 'uses':
                    uses += "%s " % ref['tagref']
                else:
                    otherrefs.append(ref)              

    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'xmlsource' : xmlsource,
            'tagname' : tagname,
            'user' : request.user,
            'loggedin' : request.user.is_authenticated(),
            'entity' : entity,
            'usedby' : usedby,
            'uses' : uses,
            'usedby' : usedby,
            'mytagl' : mytagl,
            'othertagl' : othertagl,
            'refs' : otherrefs,
        }
        return render_to_response('entitySource.html', data, RequestContext(request))

entitytypes = [
    [ 'project', 'Project - Software and computing projects in our community, packages in development' ],
    [ 'tool', 'Tool - External tools and services, open source tools, stable software packages' ],
    [ 'org', 'Organization - Community groups, experiments, universities, labs, ...' ],
    [ 'person', 'Person' ],
    [ 'meeting', 'Meeting - Meetings, workshops, conferences, seminars, tutorials of community interest' ],
    [ 'document', 'Document - Slides, poster, proceedings, paper, documentation, white paper' ],
    [ 'task', 'Task - Overview of a task area, its needs, common project potential, associated projects and tools' ],
    [ 'definition', "Definition - Concepts, general categories, things that aren't a good match for the other types" ],
    ]

orgtypes = [
    [ 'other', 'Select organization type' ],
    [ 'university', 'University' ],
    [ 'lab', 'Laboratory' ],
    [ 'facility', 'Facility' ],
    [ 'forum', 'Community forum' ],
    [ 'project', 'Project' ],
    [ 'other', 'Other' ],
    ]

documenttypes = [
    [ 'document', 'General document' ],
    [ 'slides', 'Slides' ],
    [ 'poster', 'Poster' ],
    [ 'proceedings', 'Proceedings paper' ],
    [ 'paper', 'Paper' ],
    [ 'documentation', 'Documentation' ],
    [ 'tutorial', 'Tutorial, training' ],
    [ 'white', 'White paper' ],
]

class EntityForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'
    type = forms.ChoiceField(label='Entry type', choices=entitytypes, widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }), \
        help_text="Select the sort of entry this is. May be somewhat qualitative (e.g. project vs. tool); choose what fits best. To get an idea of what classification is appropriate you can look at the currently defined <a href='/e/?type=project'>projects</a>, <a href='/e/?type=tool'>tools</a>, <a href='/e/?type=definition'>definitions</a>.")

    mytag = forms.CharField(label='Tag', widget=forms.HiddenInput() )

def makeNameTag(name):
    nametag = name.strip().lower().replace(' ','_').replace("'","")
    return nametag

class PersonForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'

    def clean_entname(self):
        exists, txt = checkExistingTag(self.cleaned_data['name'])
        return self.cleaned_data['name']

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    mytag = forms.CharField(label='Tag', widget=forms.HiddenInput() )

    type = forms.ChoiceField(label='Entry type', choices=entitytypes, initial='person', widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )

    name = forms.CharField(label='Name', max_length=200, widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Firstname Lastname. Autocomplete of names already in the DB is provided as an aid to not adding the same person again. If you re-enter the same person, any new info (associated tags, website) will be updated.")

    alltags = forms.CharField(label='Associated tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Comma separated tags associated with the person. eg. 'database' for a database expert. Tags will autocomplete so you can see what exists, or see the full list <a href='/tl/'>here</a>.")

    description_markup = forms.CharField(label='Description', widget=forms.Textarea(attrs={'rows':3}), required=False, help_text="")

    email = forms.CharField(label='email', max_length=100, required=False, widget = forms.TextInput(attrs = { 'style' : "width:200px;" }), help_text="")

    image = forms.CharField(label='Image', max_length=200, required=False, \
        help_text="Link to an image")

    web = forms.CharField(label='Website', widget=forms.Textarea(attrs={'rows':3}), required=False, help_text="Personal websites, one per line with format: url | description")

    contributor = forms.CharField(label='Contributor', widget=forms.HiddenInput())

    #uses = forms.CharField(label='Uses', max_length=400, required=False, \
    #help_text="Tags for things the person uses. Not used right now, could be a means of identifying experts.")

class MeetingForm(forms.Form):
    prepopulated_fields = {"mytag": ("date","tags")}
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    type = forms.ChoiceField(label='Entry type', choices=entitytypes, initial='meeting', widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )

    name = forms.CharField(label='Meeting title', max_length=200, help_text="")

    mytag = forms.SlugField(label='Tag name', max_length=30, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete', attrs = { 'style' : "width:200px;" }), \
        help_text="Unique tag for the meeting. Allowed characters are a-z, 0-9, -, _. Autocompletes to known tags as an aid to ensuring it is unique. If you use an existing tag, you'll be able to edit its entry (if you have rights).")

    description_markup = forms.CharField(label='Description', widget=forms.Textarea(attrs={'rows':3}), required=False, \
        help_text="Meeting description. <a href='http://daringfireball.net/projects/markdown/syntax'>Markdown formatting</a> can be used. References to other entries can be included via a hashed tag, e.g. #geant4; they are expanded to the full name and a link to the entry.")

    web = forms.CharField(label='Website', widget=forms.Textarea(attrs={'rows':3}), required=False, help_text="Meeting websites, one per line with format: url | description")

    date = forms.DateField(label='Date', required=False, widget = extras.SelectDateWidget(attrs={'style':"width:100px;"}), help_text="")

    location = forms.CharField(label='Location', max_length=200, required=False, \
        help_text = "A hashed tag (eg. #cern) can (optionally) be used to reference a tag for the location.")

    alltags = forms.CharField(label='Associated tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="e.g. 'xrootd' if it's an xrootd meeting.")

    contact = forms.CharField(label='Contact', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Meeting organizer(s) if known. Comma separated list. Autocompletes to (but not limited to) people in the DB.")

    contributor = forms.CharField(label='Contributor', max_length=400, required=True, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Contributors to this hepsoftware.org entry.")

class DocumentForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    type = forms.ChoiceField(label='Document type', choices=documenttypes, initial='document', widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )

    name = forms.CharField(label='Title', max_length=200, help_text="")

    mytag = forms.SlugField(label='Tag name', max_length=30, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete', attrs = { 'style' : "width:200px;" }), \
        help_text="Unique tag for the document. Allowed characters are a-z, 0-9, -, _. Autocompletes to known tags as an aid to ensuring it is unique. If you use an existing tag, you'll be able to edit its entry (if you have rights).")

    description_markup = forms.CharField(label='Description', widget=forms.Textarea(attrs={'rows':3}), required=False, \
        help_text="Document description or abstract. References to other entries can be included via a hashed tag, e.g. #geant4; they are expanded to the full name and a link to the entry.")

    web = forms.CharField(label='Web link', widget=forms.Textarea(attrs={'rows':3}), required=False, help_text="Web location(s) for the document, one per line with format: url | description")

    date = forms.DateField(label='Release date', required=False, widget = extras.SelectDateWidget(attrs={'style':"width:100px;"}), help_text="")

    alltags = forms.CharField(label='Associated tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Tags for e.g. the associated software project, the meeting where it was presented")

    contact = forms.CharField(label='Contact', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Lead author(s), comma separated. Autocompletes to (but not limited to) people in the DB.")

    contributor = forms.CharField(label='Contributor', widget=forms.HiddenInput())

class OrgForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'

    type = forms.ChoiceField(label='Entry type', choices=entitytypes, initial='org', widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    name = forms.CharField(label='Organization name', max_length=200, \
        help_text="An organization may be a common project, lab, university, experiment, etc.")

    mytag = forms.SlugField(label='Tag name', max_length=30, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete', attrs = { 'style' : "width:200px;" }), \
        help_text="Unique tag for the organization. Allowed characters are a-z, 0-9, -, _. Autocompletes to known tags as an aid to ensuring it is unique. If you use an existing tag, you'll be able to edit its entry (if you have rights), or create it if not existing.")

    allmytags = forms.CharField(label='Additional tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Additional tags designating this entry. e.g. both the root and rootio tags may point to the ROOT entry.")

    alltags = forms.CharField(label='Associated tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Comma separated tags associated with the organizion. eg. 'opensource' for an open source organization.")

    description_markup = forms.CharField(label='Description', widget=forms.Textarea(attrs={'rows':15}), required=False, \
        help_text="Description, not limited in length. <a href='http://daringfireball.net/projects/markdown/syntax'>Markdown formatting</a> can be used. References to other entries can be included via a hashed tag, e.g. #geant4; they are expanded to the full name and a link to the entry.")

    web = forms.CharField(label='Websites', widget=forms.Textarea(attrs={'rows':10}), required=False, help_text="Websites for the organization, one per line with format: url | description")

    image = forms.CharField(label='Image', max_length=200, required=False, \
        help_text="Link to an image to appear with the description")

    logo = forms.CharField(label='Logo', max_length=200, required=False, \
        help_text="Link to a logo image")

    phonebook = forms.CharField(label='Phonebook', max_length=200, required=False, \
        help_text="Link to phonebook, staff info page, etc. ")

    wikipedia = forms.CharField(label='Wikipedia', max_length=100, required=False, widget = forms.TextInput(attrs = { 'style' : "width:300px;" }), \
        help_text="Wiki name for this in Wikipedia, if existing. Just the wiki name, not the full URL. eg. Geant4. ")

    location = forms.CharField(label='Location', max_length=200, required=False, \
        help_text = "Location, if applicable. A hashed tag (eg. #cern) can be used to reference a tag for the location.")

    contact = forms.CharField(label='Contact', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Comma separated names (or tags) of contact people. Autocompletes to (but not limited to) people in the DB.")

    credit = forms.CharField(label='Credit', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Comma separated names of people credited for content of this entry.")

    contributor = forms.CharField(label='Contributor', max_length=400, required=True, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Contributors to this hepsoftware.org entry.")

class SoftwareForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'

    type = forms.ChoiceField(label='Entry type', choices=entitytypes, widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    name = forms.CharField(label='Name', max_length=200, help_text="")

    mytag = forms.SlugField(label='Tag name', max_length=30, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete', attrs = { 'style' : "width:200px;" }), \
        help_text="Unique tag for the entry. Allowed characters are a-z, 0-9, -, _. Autocompletes to known tags as an aid to ensuring it is unique. If you use an existing tag, you'll be able to edit its entry (if you have rights), or create it if not existing.")

    allmytags = forms.CharField(label='Additional tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Additional tags designating this entry. e.g. both the root and rootio tags may point to the ROOT entry.")

    alltags = forms.CharField(label='Associated tags', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Comma separated tags associated with this entry. eg. 'database' for a DB tool.")

    description_markup = forms.CharField(label='Description', widget=forms.Textarea(attrs={'rows':15}), required=False, \
        help_text="Full description of the entry. Not limited in length. <a href='http://daringfireball.net/projects/markdown/syntax'>Markdown formatting</a> can be used. References to other entries can be included via a hashed tag, e.g. #geant4; they are expanded to the full name and a link to the entry.")

    web = forms.CharField(label='Websites', widget=forms.Textarea(attrs={'rows':10}), required=False, help_text="Websites, one per line with format: url | description")

    uses = forms.CharField(label='Uses', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Comma separated tags of other entries that this uses. eg. for a web service based on django, include 'django'.")

    usedby = forms.CharField(label='Used by', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('EntityAutocomplete'), \
        help_text="Comma separated tags of other entries that use this.")

    contact = forms.CharField(label='Contact', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Comma separated names (or tags) of contact people. Autocompletes to (but not limited to) people in the DB.")

    credit = forms.CharField(label='Credit', max_length=400, required=False, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="People credited for content of this entry.")

    contributor = forms.CharField(label='Contributor', max_length=400, required=True, \
        widget=autocomplete_light.TextWidget('PersonAutocomplete'), \
        help_text="Contributors to this hepsoftware.org entry.")

    wikipedia = forms.CharField(label='Wikipedia', max_length=100, required=False, widget = forms.TextInput(attrs = { 'style' : "width:300px;" }), \
        help_text="Wiki name for this in Wikipedia, if existing. Just the name, not the full URL. eg. Geant4. ")

def checkExistingTag(tagname):
    tagname = makeNameTag(tagname)
    obj = Entity.objects.filter(mytag=tagname)
    if obj:
        return True, ("Tag %s already exists. Select Update if you really want to update the entry." % tagname)
    else:
        return False, ''

@login_required(login_url='/accounts/login/')
def entityForm(request, mytag=''):
    # if this is a POST request we need to process the form data
    emptyform = False
    obj = None
    if mytag == '':
        title = 'Create an entry'
    else:
        objq = Entity.objects.filter(mytag=mytag).values()
        if len(objq) > 0:
            obj = objq[0]
            title = 'Edit the entry <b>%s</b>' % obj['name']
        else:
            title = 'Create an entry for tag <b>%s</b>' % mytag

    def clean_mytag(self):
        exists, txt = checkExistingTag(self.cleaned_data['mytag'])
        return self.cleaned_data['mytag']

    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        formdata = request.POST.copy()
        title = ''
        if 'mytag' in formdata and formdata['mytag'] != '':
            title = 'Edit the entry <b>%s</b>' % formdata['name']
            mytag = formdata['mytag']
        elif mytag != '':
            formdata['mytag'] = mytag
        if request.user.is_authenticated():
            if 'contributor' not in formdata or formdata['contributor'] == '':
                formdata['contributor'] = request.user.get_full_name()
        if request.POST['type'] == 'person':
            if title == '': title = 'Add a person'
            if 'name' in request.POST and request.POST['name'] != '':
                mytag = makeNameTag(request.POST['name'])
            form = PersonForm(formdata)
        elif request.POST['type'] == 'meeting':
            if title == '': title = 'Add a meeting'
            form = MeetingForm(formdata)
        elif request.POST['type'] == 'document':
            if title == '': title = 'Add a reference to a document'
            form = DocumentForm(formdata)
        elif request.POST['type'] == 'org':
            if title == '': title = 'Add an organization'
            form = OrgForm(formdata)
        elif request.POST['type'] in ( 'project', 'tool', 'package' ):
            if title == '': title = 'Add software %s' % request.POST['type']
            form = SoftwareForm(formdata)
        elif request.POST['type'] in ( 'definition', 'task' ):
            if title == '': title = 'Add a %s' % request.POST['type']
            form = SoftwareForm(formdata)
        else:
            form = EntityForm(formdata)

        # check whether it's valid:
        if form.is_valid():
            formdata = form.cleaned_data.copy()
            if obj:
                ## Fill in the existing values
                for f in ( 'alltags', 'allmytags', 'type', ):
                    ## If the field is in the form, but value not provided, and it's in the DB, fill it from the DB
                    if f in form.fields and (f not in formdata or formdata[f] == '') and f in obj and obj[f] != None and obj[f] != '':
                        if f in ( 'alltags', 'allmytags'):
                            value = strTags(obj[f], ',', exclude = [ mytag, ])
                        else:
                            value = obj[f]
                        formdata[f] = value
                if 'save' in request.POST:
                    saveEntity(request, formdata)
                    messages.success(request, "The %s entry was updated." % mytag)
                    return entityInfo(request, mytag)
                else:
                    messages.info(request, "This entry already exists in the database. Edit as desired and then save.")
            else:
                if 'save' in request.POST:
                    saveEntity(request, formdata)
                    #messages.warning(request, "The %s entry was added." % mytag)
                    return entityInfo(request, mytag)
                else:
                    messages.info(request, "Fill in all required fields and then save.")

            # process the data in form.cleaned_data as required
            # ...
            # redirect to a new URL:
            if formdata['type'] == 'person':
                form2 = PersonForm(formdata)
            elif formdata['type'] == 'meeting':
                form2 = MeetingForm(formdata)
            elif formdata['type'] == 'document':
                form2 = DocumentForm(formdata)
            elif formdata['type'] == 'org':
                form2 = OrgForm(formdata)
            else:
                form2 = SoftwareForm(formdata)

            data = {
                'user' : request.user,
                'loggedin' : request.user.is_authenticated(),
                'form': form2,
                'emptyform' : emptyform,
                'title' : title,
            }
            return render(request, 'entryForm.html', data)
        else:
            messages.warning(request, "Please complete all required fields.")

    # if a GET (or any other method) we'll look for an entry to edit, else create a blank form
    else:
        messages.info(request, "Please complete all required fields.")
        if mytag == '':
            emptyform = True
            form = EntityForm()
        else:
            form = editEntry(request, mytag, formdata={})

    data = {
        'user' : request.user,
        'loggedin' : request.user.is_authenticated(),
        'form': form,
        'emptyform' : emptyform,
        'title' : title,
    }
    return render(request, 'entryForm.html', data)

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput())
    password2 = forms.CharField(widget=forms.PasswordInput(),label="Password (again)")

    def is_fully_valid(self):
        if self.is_valid():
            if 'password' in self.cleaned_data and 'password2' in self.cleaned_data:
                if self.cleaned_data['password'] != self.cleaned_data['password2']:
                    raise forms.ValidationError("The two password fields didn't match.")
            existing = User.objects.filter(username__iexact=self.cleaned_data['username'])
            if existing.exists():
                raise forms.ValidationError("A user with that username already exists.")
            else:
                return self.cleaned_data['username']
        return True

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password', 'password2')

def register(request):
    # get the request's context.
    context = RequestContext(request)

    # A boolean value for telling the template whether the registration was successful.
    # Set to False initially. Code changes value to True when registration succeeds.
    registered = False

    # If it's a HTTP POST, we're interested in processing form data.
    if request.method == 'POST':
        # Attempt to grab information from the raw form information.
        # Note that we make use of both UserForm and UserProfileForm.
        user_form = UserForm(data=request.POST)

        # If the two forms are valid...
        if user_form.is_fully_valid():
            # Save the user's form data to the database.
            user = user_form.save()

            # Now we hash the password with the set_password method.
            # Once hashed, we can update the user object.
            user.set_password(user.password)
            user.save()

            # Update our variable to tell the template registration was successful.
            registered = True

        # Invalid form or forms - mistakes or something else?
        # Print problems to the terminal.
        # They'll also be shown to the user.
        else:
            print 'error user', user_form.cleaned_data
            print user_form.errors

    # Not a HTTP POST, so we render our form using two ModelForm instances.
    # These forms will be blank, ready for user input.
    else:
        user_form = UserForm()

    # Render the template depending on the context.
    return render_to_response(
            'register.html',
            {'user_form': user_form, 'registered': registered},
            context)

class EntityAutocomplete(autocomplete_light.AutocompleteListBase):
    choices = AUTOCOMPLETE_ENTITIES
    autocomplete_js_attributes={'placeholder': 'Tag autocomplete is on... comma separated entries...',}

autocomplete_light.register(EntityAutocomplete)

class PersonAutocomplete(autocomplete_light.AutocompleteListBase):
    choices = PERSONS
    autocomplete_js_attributes={'placeholder': 'People autocomplete is on... comma separated entries...',}

autocomplete_light.register(PersonAutocomplete)

class EntityTypeAutocomplete(autocomplete_light.AutocompleteListBase):
    choices = ENTITY_CHOICES
    autocomplete_js_attributes={'placeholder': 'Select the entry type',}

autocomplete_light.register(PersonAutocomplete)

def strTags(tagstr, sep, exclude=[], include=[]):
    tagstr = tagstr.replace(',',' ')
    tagl = tagstr.split()
    for i in include:
        if i not in tagl: tagl.append(i)
    csv = ''
    for t in tagl:
        if t in exclude: continue
        if csv != '': csv += '%s ' % sep
        csv += t
    if csv.endswith(sep): csv = csv[:-1]
    return csv

@login_required(login_url='/accounts/login/')
def actionOnEntity(request, mytag=''):
    if not request.user.is_authenticated():
        ## not logged in, can't do nuthin'
        messages.warning(request, "You are not logged in, you cannot manage entries.")
        return mainPage(request)
    if not request.user.is_staff:
        ## general users can manage entries they have contributed to or are credited on or are a contact for
        messages.info(request, "You can manage entries you have contributed to.")
        usertag = request.user.get_full_name().lower().replace(' ','_')
        myrefs = Reference.objects.filter(tagref=usertag)
        myents = {}
        for r in myrefs:
            myents[r['entity']] = 1
        myentsl = []
        for e in myents:
            myentsl.append(e)
        myentsl.sort()
        if mytag not in myentsl:
            messages.warning(request, "You are not authorized to modify the %s entry." % mytag)
            return mainPage(request)

    if request.method == 'POST':
        requestParams = request.POST.copy()
        print 'post', requestParams
    else:
        requestParams = request.GET.copy()
        print 'get', requestParams
    if 'action' in requestParams:
        action = requestParams['action']
    else:
        messages.info(request, "No action requested")
        return mainPage(request)

    ents = Entity.objects.filter(mytag=mytag)
    if len(ents) == 0:
        messages.error(request, "Entry with tag '%s' not found." % mytag )
        return mainPage(request)
    ent = ents[0]

    if ent.state == 'deleted' and action != 'undelete':
        messages.warning(request,"The only permitted action on a deleted entry is 'undelete'.")
        return manageEntries(request)

    msg = "<a href='/e/%s/'>%s</a> update: %s" % ( mytag, mytag, action )
    messages.info(request, msg)

    if action == 'edit':
        return entityForm(request, mytag)
    elif action == 'set_draft':
        ent.state = 'draft'
        ent.save()   
    elif action == 'set_online':
        ent.state = 'online'
        ent.save()
    elif action == 'lock':
        ent.state = 'locked'
        ent.save()
    elif action == 'unlock':
        ent.state = 'online'
        ent.save()
    elif action == 'review':
        ent.state = 'review'
        ent.save()
    elif action == 'hide':
        ent.hidden = True
        ent.save()
    elif action == 'unhide':
        ent.hidden = False
        ent.save()
    elif action == 'delete':
        ent.state = 'deleted'
        ent.save()
    elif action == 'undelete':
        ent.state = 'online'
        ent.save()
    else:
        messages.warning(request, "Requested action '%s' not understood" % action)

    return manageEntries(request)

def editEntry(request, mytag, type='', form=None, formdata={}):
    objq = None
    obj = None
    objq = Entity.objects.filter(mytag=mytag).values()
    if len(objq) > 0:
        obj = objq[0]
        objtype = obj['type']
        ## Fill in the existing values
        formdata['mytag'] = mytag
        for f in ( 'mytag', 'name', 'description_markup', 'alltags', 'allmytags', 'uses', 'usedby', 'type', 'wikipedia', 'phonebook', 'email', 'image', 'logo' ):
            ## If the field is in the form, but value not provided, and it's in the DB, fill it from the DB
            if ( form == None or f in form.fields ) and (f not in formdata) and f in obj and obj[f] != None and obj[f] != '':
                if f in ( 'alltags', 'allmytags'):
                    value = strTags(obj[f], ',', exclude = [ mytag, objtype ])
                else:
                    value = obj[f]
                formdata[f] = value

        ## fields stored as references
        field = {}
        fieldlist = ( 'uses', 'usedby', 'contact', 'credit', 'contributor', 'wikipedia', 'phonebook', 'email', 'image', 'logo', 'web', )
        for f in fieldlist:
            field[f] = ''

        ## fetch the associated references
        refo = Reference.objects.filter(entity=mytag).order_by('tagref','textref').values()

        for ref in refo:
            rtype = ref['type'].strip()
            tagref = ref['tagref'].strip()
            textref = ref['textref'].strip()
            for f in fieldlist:
                if rtype == f and f == 'web':
                    field[f] += "%s | %s\n" % ( ref['textref'], ref['description'] )
                else:
                    if tagref != '':
                        if rtype == f: field[f] += '%s,' % tagref
                    elif textref != '':
                        if rtype == f: field[f] += '%s,' % textref

        if field['contributor'].find(request.user.get_full_name()) < 0:
            if field['contributor'].find(request.user.get_full_name().lower().strip().replace(' ','_')) < 0:
                field['contributor'] += ", %s" % request.user.get_full_name()


        ## references pointing to this entity
        useso = Reference.objects.filter(tagref=mytag).order_by('tagref','textref').values()
        for ref in useso:
            rtype = ref['type']
            if rtype == 'usedby':
                field['uses'] += '%s,' % ref['entity']
            elif rtype == 'wikipedia':
                field['wikipedia'] = ref['textref']
            elif rtype == 'phonebook':
                field['phonebook'] = ref['textref']
            elif rtype == 'email':
                field['email'] = ref['textref']
            elif rtype == 'image':
                field['image'] = ref['textref']
            elif rtype == 'logo':
                field['logo'] = ref['textref']
            elif rtype == 'web':
                field['web'] = ref['textref']

        for f in fieldlist:
            field[f] = cleanList(field[f])
            if field[f] != '':
                formdata[f] = field[f]

        if type == '':
            type = obj['type']
            if not form:
                if type == 'person':
                    form = PersonForm(formdata)
                elif type == 'meeting':
                    form = MeetingForm(formdata)
                elif type == 'org':
                    form = OrgForm(formdata)
                elif type in ( 'project', 'tool', 'package', 'task', 'definition', ):
                    form = SoftwareForm(formdata)
                else:
                    form = None
            else:
                form = form(formdata)

        return form
    else:
        return EntityForm({ 'mytag' : mytag })

def cleanList(list):
    listl = list.split(',')
    listd = {}
    for l in listl:
        listd[l.strip()] = 1
    lt = listd.keys()
    lt.sort()
    lts = ''
    for l in lt:
        if lts != '': lts += ', '
        lts += l
    if lts.endswith(','): lts = lts[:-1]
    if lts.startswith(','): lts = lts[1:]
    return lts

class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        else:
            return str(obj)
        return json.JSONEncoder.default(self, obj)

def compareDicts(j1, j2):
    if len(j1) != len(j2):
        return False
    t1 = j1.keys()
    t1.sort()
    t2 = j2.keys()
    t2.sort()
    if t1 != t2:
        return False
    for k in t1:
        if type(j1[k]) == type([]):
            if len(j1[k]) != len(j2[k]): return False
            if len(j1[k]) == 0: continue
            if type(j1[k][0]) == type({}):
                for i in range(0, len(j1[k])):
                    od1 = j1[k][i]
                    od2 = j2[k][i]
                    kys = od1.keys()
                    for y in kys:
                        o1 = od1[y]
                        o2 = od2[y]
                        if type(o1) == type(datetime.now()):
                            s1 = str(o1).replace('T',' ')
                            s2 = str(o2).replace('T',' ')
                            if s1 == s2: continue
                        else:
                            if o1 != o2:
                                return False
            else:
                l1 = j1[k]
                l2 = j2[k]
                for i in range(1, len(l1)):
                    if l1[i] != l2[i]:
                        return False
        if j1[k] != j2[k]:
            if type(j1[k]) == type(datetime.now()):
                s1 = str(j1[k]).replace('T',' ')
                s2 = str(j2[k]).replace('T',' ')
                if s1 == s2: continue
            elif type(j1[k]) == type(j1):
                dcompare = compareDicts(j1[k], j2[k])
                if not dcompare: 
                    return False
            elif type(j1[k]) == type([]):
                l1 = j1[k]
                l2 = j2[k]
                if l1.sort() == l2.sort():
                    continue
            else:
                return False
    return True

def saveEntity(request, fields):
    mytag = fields['mytag']
    try:
        entobj = Entity.objects.get(mytag=mytag)
    except:
        entobj = None
    if entobj:
        print 'Updating entry for', mytag
    else:
        entobj = Entity(mytag=mytag)
        print 'New entry for', mytag

    if 'name' in fields and fields['name'] != '':
        entobj.name = fields['name']
    if 'description_markup' in fields:
        entobj.description_markup = fields['description_markup']

        tmpfile = "/tmp/desc_%s_%s.txt" % ( mytag, request.user )
        tmpfilein = "/tmp/desc_%s_%s.html" % ( mytag, request.user )
        fo = codecs.open(tmpfile,'w','utf-8')
        fo.write(fields['description_markup'])
        fo.close()
        markdown = "perl %s/Markdown.pl --html4tags %s > %s" % ( PATHPREFIX, tmpfile, tmpfilein)
        cmdout = commands.getoutput(markdown)
        fi = codecs.open(tmpfilein,'r','utf-8')
        outtxt = fi.read()
        fi.close()
        outtxt = expandText(outtxt, mytag)
        if len(outtxt) > 0:
            entobj.description = outtxt

    if 'type' in fields and fields['type'] != '':
        entobj.type = fields['type']
    if 'subtype' in fields:
        entobj.subtype = fields['subtype']
    if 'date' in fields:
        entobj.date = fields['date']
    if 'location' in fields:
        entobj.location = fields['location']
    if 'allmytags' in fields:
        entobj.allmytags = strTags(fields['allmytags'], ' ', include = [ mytag, ])
    else:
        entobj.allmytags = mytag
    if 'alltags' in fields:
        entobj.alltags = strTags(fields['alltags'], ' ', exclude = [ mytag, ])

    ## Handle the references
    tagrefs = ( 'uses', 'usedby', 'contact', 'contributor', 'credit', )
    multivals = ( 'web', 'paper', 'docref', )
    for rfield in ( 'email', 'uses', 'usedby', 'wikipedia', 'phonebook', 'image', 'logo', 'location', 'web', 'contact', 'contributor', 'credit', 'image_inline', 'date', 'status', 'paper', 'docref' ):
        if rfield in fields:
            fieldvals = [] # a list of [ ref, description ] pairs
            if rfield == 'web':
                lines = fields[rfield].split('\n')
                for line in lines:
                    toks = line.split('|')
                    url = toks[0]
                    if len(toks) > 1:
                        desc = toks[1]
                    else:
                        desc = ''
                    fieldvals.append([ url, desc ])
            elif rfield in tagrefs:
                fvals = fields[rfield].split(',')
                for v in fvals:
                    v.strip()
                    toks = v.split('|')
                    v = toks[0]
                    if len(toks) > 1:
                        desc = toks[1]
                    else:
                        desc = ''                      
                    fieldvals.append([ v, desc ]) 
            else:
                fieldvals = [ [ fields[rfield], '' ], ]
            for fv in fieldvals:
                val, desc = fv
                print 'fieldval', val, desc
                update = False
                if rfield in tagrefs:
                    origval = val
                    val = val.lower().strip().replace(' ','_')
                if val == '': continue
                query = {}
                query['entity'] = mytag
                query['type'] = rfield
                if rfield in tagrefs:
                    ## For tagrefs, add it if there isn't already one matching this.
                    query['tagref'] = val
                    objs = Reference.objects.filter(**query)
                    if len(objs) > 0:
                        if objs[0].description == desc: continue
                        ## description has changed. Update.
                        update = True
                else:
                    ## for textrefs, if they are multivalue, add it if there isn't already one matching this.
                    if rfield in multivals:
                        query['textref'] = val
                        objs = Reference.objects.filter(**query)
                        if len(objs) > 0:
                            print 'found', val
                            if objs[0].description == desc: continue
                            ## description has changed. Update.
                            update = True
                    else:
                        ## if they are single value, see whether the value is being modified
                        objs = Reference.objects.filter(**query)
                        if len(objs) > 0 and objs[0].textref == val: continue
                if update:
                    if rfield in tagrefs:
                        Reference.objects.filter(**query).update(tagref=val, description=desc)
                        messages.info(request, "%s %s updated: tag ref=%s" % ( mytag, rfield, val ) )
                    else:
                        Reference.objects.filter(**query).update(textref=val, description=desc)
                        messages.info(request, "%s %s updated: ref=%s" % ( mytag, rfield, val ) )
                else:
                    ref = Reference()
                    ref.entity = mytag
                    ref.type = rfield
                    ref.description = desc
                    if rfield in tagrefs:
                        ref.tagref = val
                        ref.textref = origval
                        messages.info(request, "%s %s added: tag ref=%s" % ( mytag, rfield, val ) )
                    else:
                        ref.textref = val
                        ref.tagref = ''
                        messages.info(request, "%s %s added: ref=%s" % ( mytag, rfield, val ) )
                    ref.save()

    entobj.save()
    messages.info(request, "Entry %s saved." % mytag )
    
    ## Archive the revised entry
    entityInfo(request, name=mytag, save_to_json=True)

def expandText(txt, owntag, type='', description=''):
    ## Set up #hashlinks
    pat = re.compile('\#([a-zA-Z0-9\-\_]+)')
    for i in range (0,50):
        mat = pat.search(txt)
        if mat:
            tagname = mat.group(1).lower()
            try:
                fullname = Entity.objects.get(mytag=tagname)['name']
            except:
                title = mat.group(1)
            taglink = '<a href="/e/%s">%s</a>' % ( tagname, title )
            txt = txt.replace(mat.group(0),taglink)
            #if type in ( 'location', ):
            #    ## add tag to the associated meeting    
            #    addTag(owntag, tagname)
            #if type in ( 'talk', 'paper', ):
            #    ## add reference to the talk/paper to the associated meeting 
            #    addReferenceExe(tagname, type, '', description=txt, tagref=owntag)
        else:
            break
    txt = txt.replace(u'"',u'\\"')
    txt = txt.replace(u'[[hash]]',u'#')
    return txt

@login_required(login_url='/accounts/login/')
def manageEntries(request):
    if not request.user.is_authenticated():
        ## not logged in, can't do nuthin'
        messages.warning(request, "You are not logged in, you cannot manage entries.")
        return mainPage(request)
    query = {}
    if not request.user.is_staff:
        ## general users can manage entries they have contributed to or are credited on or are a contact for
        messages.info(request, "You can manage entries you have contributed to.")
        usertag = request.user.get_full_name().lower().replace(' ','_')
        myrefs = Reference.objects.filter(tagref=usertag)
        myents = {}
        for r in myrefs:
            myents[r['entity']] = 1
        myentsl = []
        for e in myents:
            myentsl.append(e)
        myentsl.sort()
        query['mytag__in'] = myentsl

    ## staff users can manage all
    ents = getEntities(request, query)
    ents = sorted(ents, key=lambda x:x['name'].lower())
    title = titletag = ""
    for ent in ents:
        alltagl = ent['alltags'].split()
        mytagl = ent['allmytags'].split()
        othertagl = []
        for t in alltagl:
            if t not in mytagl: othertagl.append(t)
        ent['mytagl'] = mytagl
        ent['othertagl'] = othertagl
        if ent['owner'] in PERSONS_DICT:
            ent['owner'] = "<a href='/e/%s'>%s</a>" % ( ent['owner'], PERSONS_DICT[ent['owner']] )
    if request.META.get('CONTENT_TYPE', 'text/plain') == 'application/json':
        return  HttpResponse('json', mimetype='text/html')
    else:
        data = {
            'request' : request,
            'requestParams' : request.GET,
            'user' : request.user,
            'full_name' : request.user.get_full_name(),
            'loggedin' : request.user.is_authenticated(),
            'staff' : request.user.is_staff,
            'ents': ents,
            'QUERY_TYPE' : QUERY_TYPE,
            'title' : title,
            'titletag' : titletag,
        }
        return render_to_response('manageEntries.html', data, RequestContext(request))

action_choices = [ 'edit', 'set_draft', 'set_online', 'lock', 'unlock', 'review', 'hide', 'unhide', 'delete', 'undelete', ]

class ActionForm(forms.Form):
    class Media:
        css = {"all": ("app.css",)}

    error_css_class = 'error'
    required_css_class = 'required'
    action = forms.ChoiceField(label='Action', choices=action_choices, widget=forms.Select( attrs= { 'onchange' : 'this.form.submit()' }) )
