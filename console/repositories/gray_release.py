# -*- coding: utf8 -*-

from console.models.main import AppGrayRelease


class AppGrayReleaseRepo(object):
    def create(self, **params):
        return AppGrayRelease.objects.create(**params)

    def get_by_app_id(self, app_id):
        gray = AppGrayRelease.objects.filter(app_id=app_id)
        if gray:
            return gray[0]
        return None

    def update(self, app_id, **data):
        return AppGrayRelease.objects.filter(app_id=app_id).update(**data)


gray_repo = AppGrayReleaseRepo()
