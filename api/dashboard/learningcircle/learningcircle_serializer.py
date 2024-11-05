from datetime import datetime, timedelta, timezone

import pytz
from db.learning_circle import LearningCircle, CircleMeetingLog, CircleMeetingAttendees
from rest_framework import serializers

from db.organization import Organization
from db.task import InterestGroup
from utils.types import LearningCircleRecurrenceType
from utils.utils import DateTimeUtils


class LearningCircleCreateEditSerialzier(serializers.ModelSerializer):
    ig = serializers.PrimaryKeyRelatedField(
        queryset=InterestGroup.objects.all(), required=True
    )
    org = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )

    def update(self, instance, validated_data):
        instance.ig_id = validated_data.get("ig_id", instance.ig_id)
        instance.org_id = validated_data.get("org_id", instance.org_id)
        instance.is_recurring = validated_data.get(
            "is_recurring", instance.is_recurring
        )
        instance.recurrence_type = validated_data.get(
            "recurrence_type", instance.recurrence_type
        )
        instance.recurrence = validated_data.get("recurrence", instance.recurrence)
        instance.updated_at = DateTimeUtils.get_current_utc_time()
        instance.save()
        return instance

    def create(self, validated_data):
        user_id = self.context.get("user_id")
        validated_data["created_by_id"] = user_id
        return LearningCircle.objects.create(**validated_data)

    def validate(self, attrs):
        is_recurring = attrs.get("is_recurring")
        recurrence_type = attrs.get("recurrence_type")
        recurrence = attrs.get("recurrence")
        if not is_recurring:
            attrs["recurrence_type"] = None
            attrs["recurrence"] = None
        else:
            if not recurrence_type or not recurrence:
                raise serializers.ValidationError(
                    "Recurrence type and recurrence are required for recurring learning circles"
                )
            if recurrence_type not in LearningCircleRecurrenceType.get_all_values():
                raise serializers.ValidationError("Invalid recurrence type.")
            if recurrence_type == LearningCircleRecurrenceType.WEEKLY.value:
                if recurrence < 1 or recurrence > 7:
                    raise serializers.ValidationError(
                        "Recurrence should be between 1 and 7 for weekly learning circles"
                    )
            elif recurrence_type == LearningCircleRecurrenceType.MONTHLY.value:
                if recurrence < 1 or recurrence > 28:
                    raise serializers.ValidationError(
                        "Recurrence should be between 1 and 28 for monthly learning circles"
                    )
        return super().validate(attrs)

    class Meta:
        model = LearningCircle
        fields = ["ig", "org", "is_recurring", "recurrence_type", "recurrence"]


class LearningCircleListSerializer(serializers.ModelSerializer):
    ig = serializers.CharField(source="ig.name", read_only=True)
    org = serializers.CharField(source="org.name", read_only=True, allow_null=True)
    created_by = serializers.CharField(source="created_by_id.full_name", read_only=True)
    next_meetup = serializers.SerializerMethodField()

    def _get_next_weekday(self, target_day: int):
        today = datetime.now()
        current_day = today.isoweekday() + 2
        current_day = current_day if current_day <= 7 else 1
        days_until_next = ((target_day - current_day + 7) % 7) + 1
        days_until_next = days_until_next or 7
        next_day_date = today + timedelta(days=days_until_next)
        return next_day_date.date()

    def _get_month_day(self, target_day: int):
        today = datetime.now()
        current_day = today.day
        current_month = today.month
        current_year = today.year
        if current_day >= target_day:
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        return datetime(current_year, current_month, target_day).date()

    def get_next_meetup(self, obj):
        next_meetup = (
            CircleMeetingLog.objects.filter(circle_id=obj.id)
            .filter(
                # meet_time__gte=DateTimeUtils.get_current_utc_time(),
                is_report_submitted=False,
            )
            .order_by("-meet_time")
            .first()
        )
        if next_meetup:
            return {
                **CircleMeetingLogListSerializer(next_meetup).data,
                "is_scheduled": True,
            }
        if not obj.is_recurring:
            return None
        if obj.recurrence_type == LearningCircleRecurrenceType.WEEKLY.value:
            return {
                "is_scheduled": False,
                "meet_time": self._get_next_weekday(obj.recurrence),
            }
        if obj.recurrence_type == LearningCircleRecurrenceType.MONTHLY.value:
            return {
                "is_scheduled": False,
                "meet_time": self._get_month_day(obj.recurrence),
            }
        return {"is_scheduled": False, "meet_time": None}

    class Meta:
        model = LearningCircle
        fields = [
            "id",
            "ig",
            "org",
            "is_recurring",
            "recurrence_type",
            "recurrence",
            "created_by",
            "next_meetup",
        ]


class CircleMeetingLogCreateEditSerializer(serializers.ModelSerializer):
    circle_id = serializers.PrimaryKeyRelatedField(
        queryset=LearningCircle.objects.all(), required=True
    )

    def update(self, instance, validated_data):
        instance.title = validated_data.get("title", instance.title)
        instance.is_report_needed = validated_data.get(
            "is_report_needed", instance.is_report_needed
        )
        instance.report_description = validated_data.get(
            "report_description", instance.report_description
        )
        instance.coord_x = validated_data.get("coord_x", instance.coord_x)
        instance.coord_y = validated_data.get("coord_y", instance.coord_y)
        instance.meet_place = validated_data.get("meet_place", instance.meet_place)
        instance.meet_time = validated_data.get("meet_time", instance.meet_time)
        instance.duration = validated_data.get("duration", instance.duration)
        instance.updated_at = DateTimeUtils.get_current_utc_time()
        instance.save()
        return instance

    def create(self, validated_data):
        user_id = self.context.get("user_id")
        meet_code = self.context.get("meet_code")
        validated_data["created_by_id"] = user_id
        validated_data["meet_code"] = meet_code
        meet = CircleMeetingLog.objects.create(**validated_data)
        CircleMeetingAttendees.objects.create(
            meet_id=meet, user_id_id=user_id, is_joined=True, joined_at=datetime.now()
        )
        return meet

    def validate(self, attrs):
        is_report_needed = attrs.get("is_report_needed")
        report_description = attrs.get("report_description")
        if not is_report_needed:
            attrs["report_description"] = None
        else:
            if not report_description:
                raise serializers.ValidationError("Report description is required")
        return super().validate(attrs)

    def validate_circle_id(self, value):
        if CircleMeetingLog.objects.filter(
            circle_id=value, is_report_submitted=False
        ).exists():
            raise serializers.ValidationError(
                "There is already an ongoing meeting for this learning circle"
            )
        return value

    class Meta:
        model = CircleMeetingLog
        fields = [
            "circle_id",
            "title",
            "is_report_needed",
            "report_description",
            "coord_x",
            "coord_y",
            "meet_place",
            "meet_time",
            "duration",
        ]


class CircleMeetingLogListSerializer(serializers.ModelSerializer):
    circle = serializers.CharField(source="circle_id.id", read_only=True)
    created_by = serializers.CharField(source="created_by_id.full_name", read_only=True)
    is_started = serializers.SerializerMethodField()
    is_ended = serializers.SerializerMethodField()

    def get_is_started(self, obj):
        return obj.meet_time <= DateTimeUtils.get_current_utc_time()

    def get_is_ended(self, obj):
        return (obj.meet_time + timedelta(hours=obj.duration + 1)) <= datetime.now(
            timezone.utc
        )

    class Meta:
        model = CircleMeetingLog
        fields = [
            "id",
            "circle",
            "meet_code",
            "title",
            "is_report_needed",
            "report_description",
            "coord_x",
            "coord_y",
            "meet_place",
            "meet_time",
            "duration",
            "created_by",
            "is_started",
            "is_ended",
            "is_report_submitted",
        ]


class CircleMeetingAttendeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = CircleMeetingAttendees
        fields = ["is_joined", "is_report_submitted", "is_lc_approved"]


class CircleMeetupInfoSerializer(serializers.ModelSerializer):
    title = serializers.CharField(read_only=True)
    is_report_needed = serializers.BooleanField(read_only=True)
    report_description = serializers.CharField(read_only=True)
    coord_x = serializers.FloatField(read_only=True)
    coord_y = serializers.FloatField(read_only=True)
    meet_place = serializers.CharField(read_only=True)
    meet_time = serializers.DateTimeField(read_only=True)
    duration = serializers.IntegerField(read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    is_started = serializers.SerializerMethodField()
    is_ended = serializers.SerializerMethodField()
    attendee = serializers.SerializerMethodField()

    def get_is_started(self, obj):
        return obj.meet_time <= DateTimeUtils.get_current_utc_time()

    def get_is_ended(self, obj):
        return (obj.meet_time + timedelta(hours=obj.duration + 1)) <= datetime.now(
            timezone.utc
        )

    def get_attendee(self, obj):
        if user_id := self.context.get("user_id"):
            user_obj = obj.circle_meeting_attendance_meet_id.filter(
                user_id=user_id
            ).first()
            if not user_obj:
                return None
            return CircleMeetingAttendeeSerializer(
                user_obj,
                many=False,
            ).data
        return None

    class Meta:
        model = CircleMeetingLog
        fields = [
            "id",
            "title",
            "is_report_needed",
            "report_description",
            "coord_x",
            "coord_y",
            "meet_place",
            "meet_time",
            "duration",
            "is_approved",
            "is_started",
            "is_ended",
            "attendee",
        ]
