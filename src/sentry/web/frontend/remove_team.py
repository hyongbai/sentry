from __future__ import absolute_import

from django import forms
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext_lazy as _

from sentry.models import (
    AuditLogEntry, AuditLogEntryEvent, OrganizationMemberType, TeamStatus
)
from sentry.permissions import can_remove_team
from sentry.tasks.deletion import delete_team
from sentry.web.frontend.base import TeamView


class RemoveTeamForm(forms.Form):
    pass


class RemoveTeamView(TeamView):
    required_access = OrganizationMemberType.ADMIN
    sudo_required = True

    def get_form(self, request):
        if request.method == 'POST':
            return RemoveTeamForm(request.POST)
        return RemoveTeamForm(None)

    def handle(self, request, organization, team):
        if not can_remove_team(request.user, team):
            return HttpResponseRedirect(reverse('sentry'))

        form = self.get_form(request)

        if form.is_valid():
            team.update(status=TeamStatus.PENDING_DELETION)

            # we delay the task for 5 minutes so we can implement an undo
            kwargs = {'object_id': team.id}
            delete_team.apply_async(kwargs=kwargs, countdown=60 * 5)

            AuditLogEntry.objects.create(
                organization=organization,
                actor=request.user,
                ip_address=request.META['REMOTE_ADDR'],
                target_object=team.id,
                event=AuditLogEntryEvent.TEAM_REMOVE,
                data=team.get_audit_log_data(),
            )

            messages.add_message(
                request, messages.SUCCESS,
                _(u'The team %r was scheduled for deletion.') % (team.name.encode('utf-8'),))

            return HttpResponseRedirect(reverse('sentry'))

        context = {
            'form': form,
        }

        return self.respond('sentry/teams/remove.html', context)
