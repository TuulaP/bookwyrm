''' import books from another app '''
from io import TextIOWrapper

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils.decorators import method_decorator
from django.views import View

from bookwyrm import forms, goodreads_import, models
from bookwyrm.tasks import app

# pylint: disable= no-self-use
@method_decorator(login_required, name='dispatch')
class Import(View):
    ''' import view '''
    def get(self, request):
        ''' load import page '''
        return TemplateResponse(request, 'import.html', {
            'title': 'Import Books',
            'import_form': forms.ImportForm(),
            'jobs': models.ImportJob.
                    objects.filter(user=request.user).order_by('-created_date'),
        })

    def post(self, request):
        ''' ingest a goodreads csv '''
        form = forms.ImportForm(request.POST, request.FILES)
        if form.is_valid():
            include_reviews = request.POST.get('include_reviews') == 'on'
            privacy = request.POST.get('privacy')
            try:
                job = goodreads_import.create_job(
                    request.user,
                    TextIOWrapper(
                        request.FILES['csv_file'],
                        encoding=request.encoding),
                    include_reviews,
                    privacy,
                )
            except (UnicodeDecodeError, ValueError):
                return HttpResponseBadRequest('Not a valid csv file')
            goodreads_import.start_import(job)
            return redirect('/import/%d' % job.id)
        return HttpResponseBadRequest()


@method_decorator(login_required, name='dispatch')
class ImportStatus(View):
    ''' status of an existing import '''
    def get(self, request, job_id):
        ''' status of an import job '''
        job = models.ImportJob.objects.get(id=job_id)
        if job.user != request.user:
            raise PermissionDenied
        task = app.AsyncResult(job.task_id)
        items = job.items.order_by('index').all()
        failed_items = [i for i in items if i.fail_reason]
        items = [i for i in items if not i.fail_reason]
        return TemplateResponse(request, 'import_status.html', {
            'title': 'Import Status',
            'job': job,
            'items': items,
            'failed_items': failed_items,
            'task': task
        })

    def post(self, request, job_id):
        ''' retry lines from an import '''
        job = get_object_or_404(models.ImportJob, id=job_id)
        items = []
        for item in request.POST.getlist('import_item'):
            items.append(get_object_or_404(models.ImportItem, id=item))

        job = goodreads_import.create_retry_job(
            request.user,
            job,
            items,
        )
        goodreads_import.start_import(job)
        return redirect('/import/%d' % job.id)
