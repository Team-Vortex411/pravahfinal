from django.contrib import admin

from accounts.models import Department, User
from applications.models import Application
from pilots.models import Pilot
from problem_statements.models import ProblemStatement
from startups.models import Startup

admin.site.register(Department)
admin.site.register(User)
admin.site.register(ProblemStatement)
admin.site.register(Startup)
admin.site.register(Application)
admin.site.register(Pilot)
