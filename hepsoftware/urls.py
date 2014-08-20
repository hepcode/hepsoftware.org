from django.conf.urls import patterns, include, url
from django.views.generic.edit import CreateView
from django.contrib.auth.forms import UserCreationForm

# Uncomment the next two lines to enable the admin:
from django.contrib import admin

import autocomplete_light

autocomplete_light.autodiscover()
admin.autodiscover()

from hepsoftware import views as hepswviews

urlpatterns = patterns('',
    url(r'^$', hepswviews.mainPage, name='index'),
    url(r'^/$', hepswviews.mainPage, name='index'),

    url(r'^e/$', hepswviews.entityInfo, name='entityInfo'),
    url(r'^e/(?P<name>.*)/$', hepswviews.entityInfo, name='entityInfo'),
    url(r'^el/$', hepswviews.entityList, name='entityList'),
    url(r'^tl/$', hepswviews.tagList, name='tagList'),
    url(r'^rl/$', hepswviews.referList, name='referList'),
    
    url(r'^/e/$', hepswviews.entityInfo, name='entityInfo'),
    url(r'^/e/(?P<name>.*)/$', hepswviews.entityInfo, name='entityInfo'),
    url(r'^/el/$', hepswviews.entityList, name='entityList'),
    url(r'^/tl/$', hepswviews.tagList, name='tagList'),
    url(r'^/rl/$', hepswviews.referList, name='referList'),

    url(r'^/me/$', hepswviews.manageEntries, name='manageEntries'),
    url(r'^me/$', hepswviews.manageEntries, name='manageEntries'),

    url(r'^s/$', hepswviews.viewSource, name='viewSource'),
    url(r'^s/(?P<name>.*)/$', hepswviews.viewSource, name='viewSource'),

    url(r'^my/$', hepswviews.userContribs, name='userContribs'),
    url(r'^user/(?P<username>.*)/$', hepswviews.userContribs, name='userContribs'),

    url(r'^in/$', hepswviews.entityForm, name='entityForm'),
    url(r'^in/(?P<mytag>.*)/$', hepswviews.entityForm, name='entityForm'),

    url(r'^act/$', hepswviews.actionOnEntity, name='actionOnEntity'),
    url(r'^act/(?P<mytag>.*)/$', hepswviews.actionOnEntity, name='actionOnEntity'),

    # Uncomment the admin/doc line below to enable admin documentation:
    #url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),                                                                                                                                                                                  

    url(r'^register/$', hepswviews.register, name='register'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login'),
    url(r'^accounts/logout/$', 'django.contrib.auth.views.logout'),

    #url('^register/', CreateView.as_view(
    #        template_name='registration/new.html',
    #        form_class=UserCreationForm,
    #        success_url='/')),

    url(r'^autocomplete/', include('autocomplete_light.urls')),
             
)
