from django.db import models

class Entity(models.Model):
    ## types of entity: org, person, sw package, facility, ...
    ## mytag: the identifying tag owned by this entity
    mytag = models.CharField('mytag_id', max_length=100, unique=True)
    name = models.CharField('name', max_length=200, unique=False)
    type = models.CharField('type', max_length=100, unique=False, null=True)
    subtype = models.CharField('subtype', max_length=100, unique=False, null=True)
    description = models.TextField('description', null=True)
    description_markup = models.TextField('description_html', null=True)
    web = models.TextField('web', unique=False, null=True)    
    date = models.DateTimeField('date', null=True)    
    location = models.CharField('location', max_length=100, unique=False, null=True)
    allmytags = models.CharField('allmytags', max_length=200, unique=False, null=True) # allmytags: all tags owned by this entity
    alltags = models.CharField('alltags', max_length=500, unique=False, null=True) # tagstring: all tags associated with this entity
    created_at = models.DateTimeField('created_at', auto_now_add=True, null=False)
    updated_at = models.DateTimeField('updated_at', auto_now=True, null=False)
    hidden = models.BooleanField('date', null=False, default=False)    
    state = models.CharField('state', max_length=30, unique=False, null=True)
    owner = models.CharField('owner', max_length=100, unique=False, null=True)

    def get_absolute_url(self):
        return "/e/%s" % self.mytag.encode('utf8','ignore')
    def __str__(self):
        return '%s' % self.mytag.encode('utf8','ignore')
    def __unicode__(self):
        return self.mytag.encode('utf8','ignore')

class Tag(models.Model):
    # types of tag: primary key of an entity (org, person, ...); glossary entry
    name = models.CharField('name', max_length=100, unique=True)
    type = models.CharField('type', max_length=100, unique=False, null=True)
    subtype = models.CharField('subtype', max_length=100, unique=False, null=True)
    description = models.CharField('description', max_length=200, unique=False, null=True)  # describe the tag
    description_original = models.CharField('description', max_length=200, unique=False, null=True)  # describe the tag
    implicit = models.CharField('description', max_length=200, unique=False, null=True)  # describe the tag
    created_at = models.DateTimeField('created_at', auto_now_add=True, null=False)
    updated_at = models.DateTimeField('updated_at', auto_now=True, null=False)

class Reference(models.Model):
    # Reference from an entity (org, person, etc.) to something. Types of reference: institute, wikipedia, uses, hastag, linkedin, ...
    entity = models.CharField('entity', max_length=100, unique=False)
    type = models.CharField('type', max_length=100, unique=False, null=True) # type of reference
    subtype = models.CharField('subtype', max_length=100, unique=False, null=True)
    description = models.CharField('description', max_length=200, null=True)  # describe the reference (optional)
    entityref = models.CharField('entityref', max_length=100, unique=False, null=True) # if the reference is to an Entity
    tagref = models.CharField('tagref', max_length=100, unique=False, null=True) # if the reference is to an Entity
    textref = models.CharField('textref', max_length=200, unique=False, null=True) # reference
    textref_original = models.CharField('textref', max_length=200, unique=False, null=True) # reference
    created_at = models.DateTimeField('created_at', auto_now_add=True, null=False)
    updated_at = models.DateTimeField('updated_at', auto_now=True, null=False)
    hidden = models.BooleanField('date', null=False, default=False)    
