import pytest

from attendx.core.validators import (
    RegistrationData, ValidationError, normalize_account_id, normalize_name,
    normalize_sex, normalize_spaces, validate_time_range,
)


def valid_student(**overrides):
    data = {
        "account_id": " S-100 ", "role": " student ", "password": "secure-password",
        "confirm_password": "secure-password", "first_name": "  Ana   Mae ", "last_name": " Dela Cruz ",
        "middle_name": "  Marie  ", "suffix": "", "sex": "female", "course": " BSIT ",
        "year_level": "2", "section": "A", "recovery_email": " Ana@example.com ",
    }
    data.update(overrides)
    return data


def test_normalize_spaces_and_account_id():
    assert normalize_spaces("  Ana   Mae   ") == "Ana Mae"
    assert normalize_account_id(" S-100 ") == "s-100"


@pytest.mark.parametrize("value", ["", "has space", "has/slash", "?bad", "a" * 65])
def test_invalid_account_ids_are_rejected(value):
    with pytest.raises(ValidationError):
        normalize_account_id(value)


def test_name_validation_trims_spaces_and_rejects_digits():
    assert normalize_name("  Ana   Mae ", "First Name") == "Ana Mae"
    assert normalize_name("  ", "Middle Name", required=False) is None
    with pytest.raises(ValidationError):
        normalize_name("Ana2", "First Name")
    with pytest.raises(ValidationError):
        normalize_name("", "First Name")


def test_sex_is_limited_to_male_or_female():
    assert normalize_sex(" female ") == "Female"
    with pytest.raises(ValidationError):
        normalize_sex("Other")


def test_student_registration_normalizes_fields():
    data = RegistrationData.build(**valid_student())
    assert data.role == "STUDENT"
    assert data.account_id == "s-100"
    assert data.first_name == "Ana Mae"
    assert data.middle_name == "Marie"
    assert data.sex == "Female"
    assert data.recovery_email == "ana@example.com"


def test_tc_role_and_mismatched_password_rejected():
    with pytest.raises(ValidationError, match="Only Teacher and Student"):
        RegistrationData.build(**valid_student(role="TC"))
    with pytest.raises(ValidationError, match="do not match"):
        RegistrationData.build(**valid_student(confirm_password="not-the-same"))


def test_student_requires_course_year_and_section():
    with pytest.raises(ValidationError, match="Course, Year, and Section"):
        RegistrationData.build(**valid_student(section=""))


def test_time_range_validation():
    assert validate_time_range("08:00:00", "09:30") == ("08:00", "09:30")
    with pytest.raises(ValidationError):
        validate_time_range("08:00", "08:00")
    with pytest.raises(ValidationError):
        validate_time_range("23:00", "01:00")
