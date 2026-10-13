from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from sqlalchemy.exc import IntegrityError
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv

import json
import os
import random
import traceback

from model import (
    db,
    User,
    EnergyDemandProjection,
    DailyProfile,
    Location
)


# ============================================================
# APP / DATABASE CONFIGURATION
# ============================================================


app = Flask(__name__)

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False


# ============================================================
# DATABASE
#
# For Render/Aiven:
#
# Option 1:
# DATABASE_URL=mysql+pymysql://...
#
# OR
#
# MYSQL_USER
# MYSQL_PASSWORD
# MYSQL_HOST
# MYSQL_PORT
# MYSQL_DATABASE
# ============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    ""
).strip()


if DATABASE_URL:

    if DATABASE_URL.startswith(
        "mysql://"
    ):

        DATABASE_URL = (
            DATABASE_URL.replace(
                "mysql://",
                "mysql+pymysql://",
                1
            )
        )


    app.config[
        "SQLALCHEMY_DATABASE_URI"
    ] = DATABASE_URL


else:

    mysql_user = os.getenv(
        "MYSQL_USER",
        "root"
    )

    mysql_password = os.getenv(
        "MYSQL_PASSWORD",
        ""
    )

    mysql_host = os.getenv(
        "MYSQL_HOST",
        "localhost"
    )

    mysql_port = os.getenv(
        "MYSQL_PORT",
        "3306"
    )

    mysql_database = os.getenv(
        "MYSQL_DATABASE",
        "nrhess"
    )


    app.config[
        "SQLALCHEMY_DATABASE_URI"
    ] = (

        f"mysql+pymysql://"
        f"{mysql_user}:"
        f"{mysql_password}@"
        f"{mysql_host}:"
        f"{mysql_port}/"
        f"{mysql_database}"

    )


# ============================================================
# OPTIONAL MYSQL SSL
# ============================================================

mysql_ssl_ca = os.getenv(
    "MYSQL_SSL_CA",
    ""
).strip()


if mysql_ssl_ca:

    app.config[
        "SQLALCHEMY_ENGINE_OPTIONS"
    ] = {

        "connect_args": {

            "ssl": {

                "ca":
                    mysql_ssl_ca

            }

        }

    }


# ============================================================
# CORS
# ============================================================

frontend_origin = os.getenv(
    "FRONTEND_ORIGIN",
    "*"
).strip() or "*"


CORS(
    app,
    resources={
        r"/api/*": {
            "origins":
                frontend_origin
        }
    }
)


db.init_app(app)

bcrypt = Bcrypt(app)


# ============================================================
# HOME
# ============================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "message":
            "RHES backend is running"

    }), 200


# ============================================================
# COLLABORATION / ROLE AUTHENTICATION
# DISABLED
# ============================================================

"""
The following newer collaboration features
are intentionally disabled in this deployment:

- Admin role approval
- Requested roles
- Assigned locations
- Bearer-token authentication
- role_required()
- /api/admin/users
- /api/me
- Collaboration agents
- Multi-agent negotiation
- Collaboration runs

Normal RHES username/password login is
still active below.
"""


# ============================================================
# HURRICANE / RESILIENCY / SMR
# DISABLED
# ============================================================

"""
The following are intentionally disabled:

- Hurricane calculator
- Hurricane case study
- /api/run_resiliency
- S0-S5 scenarios
- LORPA
- IRL framework
- SMR human-performance evaluation
- Multi-energy resiliency
- Hydrogen-Thermal resiliency network

The main simulator only uses:

1. Electricity
2. Hydrogen
3. Thermal
"""


# ============================================================
# BASIC HELPERS
# ============================================================

def _safe_float(
    value,
    default=0.0
):

    try:

        if (
            value is None
            or value == ""
        ):

            return float(
                default
            )


        return float(
            value
        )


    except (
        TypeError,
        ValueError
    ):

        return float(
            default
        )


def _safe_int(
    value,
    default=0
):

    try:

        if (
            value is None
            or value == ""
        ):

            return int(
                default
            )


        return int(
            value
        )


    except (
        TypeError,
        ValueError
    ):

        return int(
            default
        )


def _fraction(
    value,
    default=0.0
):

    number = _safe_float(
        value,
        default
    )


    if number > 1:

        return (
            number / 100.0
        )


    return number


def _simulation_years(
    start_year,
    end_year
):

    available_years = [

        2025,
        2030,
        2035,
        2040,
        2045,
        2050,
        2055,
        2060,
        2100

    ]


    start_year = int(
        start_year
    )

    end_year = int(
        end_year
    )


    return [

        year

        for year
        in available_years

        if (
            start_year
            <= year
            <= end_year
        )

    ]


def _compute_crf(
    rate,
    lifetime
):

    if lifetime <= 0:

        return 0.0


    return (

        rate
        * (
            1 + rate
        ) ** lifetime

    ) / (

        (
            1 + rate
        ) ** lifetime

        - 1

    )


def _find_source_by_type(
    sources,
    source_type
):

    wanted = str(
        source_type
        or ""
    ).strip().lower()


    for source in (
        sources
        or []
    ):

        if not isinstance(
            source,
            dict
        ):

            continue


        technology = str(

            source.get(
                "type"
            )

            or source.get(
                "technology"
            )

            or ""

        ).strip().lower()


        description = str(

            source.get(
                "description"
            )

            or ""

        ).strip().lower()


        if (
            technology == wanted
            or wanted in description
        ):

            return source


    return None


# ============================================================
# LOCATION SIZING LIMIT MODEL
# ============================================================
#
# Uses V2 table so an older
# location_sizing_limits table does not
# cause a source_id schema error.
# ============================================================

class LocationSizingLimit(
    db.Model
):

    __tablename__ = (
        "location_sizing_limits_v2"
    )


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    user_id = db.Column(
        db.Integer,
        nullable=True,
        index=True
    )


    location_name = db.Column(
        db.String(150),
        nullable=False,
        index=True
    )


    source_id = db.Column(
        db.Integer,
        nullable=False,
        index=True
    )


    source_type = db.Column(
        db.String(100),
        nullable=False
    )


    sizing_limits = db.Column(
        db.Text,
        nullable=False,
        default="{}"
    )


    __table_args__ = (

        db.UniqueConstraint(

            "location_name",
            "source_id",

            name=
                "uq_location_source_sizing_v2"

        ),

    )


    def to_dict(self):

        try:

            limits = json.loads(

                self.sizing_limits
                or "{}"

            )

        except (
            TypeError,
            ValueError
        ):

            limits = {}


        return {

            "id":
                self.id,

            "user_id":
                self.user_id,

            "location_name":
                self.location_name,

            "source_id":
                self.source_id,

            "source_type":
                self.source_type,

            "sizing_limits":
                limits

        }


# ============================================================
# SIZING HELPERS
# ============================================================

def _normalize_sizing_limits(
    limits
):

    if not isinstance(
        limits,
        dict
    ):

        return {}


    cleaned = {}


    for (
        year,
        value
    ) in limits.items():


        if (
            value is None
            or value == ""
        ):

            continue


        try:

            cleaned[
                str(year)
            ] = float(
                value
            )


        except (
            TypeError,
            ValueError
        ):

            continue


    return cleaned


def _load_location_sizing_limits(
    location_name
):

    if not location_name:

        return {}


    rows = (

        LocationSizingLimit
        .query
        .filter_by(

            location_name=
                str(
                    location_name
                ).strip()

        )
        .all()

    )


    result = {}


    for row in rows:

        try:

            limits = json.loads(

                row.sizing_limits
                or "{}"

            )

        except (
            TypeError,
            ValueError
        ):

            limits = {}


        result[
            str(
                row.source_id
            )
        ] = {

            "source_id":
                row.source_id,

            "source_type":
                row.source_type,

            "sizing_limits":
                limits

        }


    return result


def _get_region_sizing_limit(
    location_name,
    source_id,
    year,
    fallback=0.0
):

    if (
        not location_name
        or source_id is None
    ):

        return _safe_float(
            fallback,
            0
        )


    try:

        source_id = int(
            source_id
        )

    except (
        TypeError,
        ValueError
    ):

        return _safe_float(
            fallback,
            0
        )


    row = (

        LocationSizingLimit
        .query
        .filter_by(

            location_name=
                str(
                    location_name
                ).strip(),

            source_id=
                source_id

        )
        .first()

    )


    if not row:

        return _safe_float(
            fallback,
            0
        )


    try:

        limits = json.loads(

            row.sizing_limits
            or "{}"

        )

    except (
        TypeError,
        ValueError
    ):

        return _safe_float(
            fallback,
            0
        )


    value = limits.get(
        str(year)
    )


    if value is None:

        return _safe_float(
            fallback,
            0
        )


    return _safe_float(
        value,
        fallback
    )


def _get_source_capacity_for_year(
    source,
    year,
    region_name=None
):

    if not source:

        return 0.0


    limits = (

        source.get(
            "sizing_limits"
        )

        or source.get(
            "sizingLimits"
        )

        or {}

    )


    fallback = _safe_float(

        limits.get(

            str(year),

            limits.get(
                year,
                0
            )

        ),

        0

    )


    if region_name:

        return _get_region_sizing_limit(

            location_name=
                region_name,

            source_id=
                source.get(
                    "id"
                ),

            year=
                year,

            fallback=
                fallback

        )


    return fallback


# ============================================================
# NORMAL REGISTRATION
# ============================================================

@app.route(
    "/api/register",
    methods=["POST"]
)
def register():

    data = request.get_json(
        silent=True
    ) or {}


    username = str(

        data.get(
            "username"
        )

        or ""

    ).strip()


    password = (

        data.get(
            "password"
        )

        or ""

    )


    if not username:

        return jsonify({

            "error":
                "Username is required"

        }), 400


    if len(password) < 8:

        return jsonify({

            "error":
                "Password must contain at least 8 characters"

        }), 400


    existing = User.query.filter_by(

        name=
            username

    ).first()


    if existing:

        return jsonify({

            "error":
                "Username already exists"

        }), 409


    hashed_password = (

        bcrypt
        .generate_password_hash(
            password
        )
        .decode(
            "utf-8"
        )

    )


    new_user = User(

        name=
            username,

        password=
            hashed_password

    )


    try:

        db.session.add(
            new_user
        )


        db.session.commit()


        return jsonify({

            "message":
                "Registration successful."

        }), 201


    except IntegrityError:

        db.session.rollback()


        return jsonify({

            "error":
                "Username already exists"

        }), 409


    except Exception as error:

        db.session.rollback()


        traceback.print_exc()


        return jsonify({

            "error":
                "Registration failed",

            "details":
                str(error)

        }), 500


# ============================================================
# NORMAL LOGIN
# ============================================================

@app.route(
    "/api/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    ) or {}


    username = str(

        data.get(
            "username"
        )

        or ""

    ).strip()


    password = (

        data.get(
            "password"
        )

        or ""

    )


    user = User.query.filter_by(

        name=
            username

    ).first()


    if (

        not user

        or not bcrypt
            .check_password_hash(

                user.password,
                password

            )

    ):

        return jsonify({

            "error":
                "Invalid username or password"

        }), 401


    return jsonify({

        "message":
            "Login successful",

        "userId":
            user.id,

        "username":
            user.name

    }), 200


# ============================================================
# RESET PASSWORD
# ============================================================

@app.route(
    "/api/reset_password",
    methods=["POST"]
)
def reset_password():

    data = request.get_json(
        silent=True
    ) or {}


    username = str(

        data.get(
            "username"
        )

        or ""

    ).strip()


    new_password = (

        data.get(
            "new_password"
        )

        or ""

    )


    if (
        not username
        or not new_password
    ):

        return jsonify({

            "error":
                "Missing fields"

        }), 400


    if len(
        new_password
    ) < 8:

        return jsonify({

            "error":
                "Password must contain at least 8 characters"

        }), 400


    user = User.query.filter_by(

        name=
            username

    ).first()


    if not user:

        return jsonify({

            "error":
                "User not found"

        }), 404


    user.password = (

        bcrypt
        .generate_password_hash(
            new_password
        )
        .decode(
            "utf-8"
        )

    )


    db.session.commit()


    return jsonify({

        "message":
            "Password reset successful"

    }), 200


# ============================================================
# ENERGY DEMAND
# ============================================================

@app.route(
    "/api/energy_demand",
    methods=["POST"]
)
def save_energy_demand():

    try:

        data = (
            request.get_json()
            or {}
        )


        user_id = data[
            "user_id"
        ]


        name = str(
            data[
                "name"
            ]
        ).strip()


        demand_by_year = data[
            "demand_per_year"
        ]


        if not isinstance(
            demand_by_year,
            dict
        ):

            return jsonify({

                "error":
                    "demand_per_year must be an object"

            }), 400


        cleaned_power = {}

        energy_by_year = {}


        for (
            year,
            power
        ) in demand_by_year.items():


            try:

                power_value = float(
                    power
                )


            except (
                TypeError,
                ValueError
            ):

                return jsonify({

                    "error":
                        f"Invalid power value for year {year}: {power}"

                }), 400


            cleaned_power[
                str(year)
            ] = power_value


            energy_by_year[
                str(year)
            ] = round(

                power_value
                * 8760

            )


        full_demand = {

            "power":
                cleaned_power,

            "energy":
                energy_by_year

        }


        existing = (

            EnergyDemandProjection
            .query
            .filter_by(

                user_id=
                    user_id,

                name=
                    name

            )
            .first()

        )


        if existing:

            existing.base_demand = 0

            existing.growth_rate = (
                json.dumps(
                    full_demand
                )
            )


        else:

            count = (

                EnergyDemandProjection
                .query
                .filter_by(
                    user_id=
                        user_id
                )
                .count()

            )


            if count >= 10:

                return jsonify({

                    "error":
                        "Max 10 projections allowed"

                }), 400


            projection = (
                EnergyDemandProjection(

                    name=
                        name,

                    base_demand=
                        0,

                    growth_rate=
                        json.dumps(
                            full_demand
                        ),

                    user_id=
                        user_id

                )
            )


            db.session.add(
                projection
            )


        db.session.commit()


        return jsonify({

            "message":
                "Projection saved",

            "energy_per_year":
                energy_by_year

        }), 200


    except Exception as error:

        db.session.rollback()


        traceback.print_exc()


        return jsonify({

            "error":
                "Server error",

            "details":
                str(error)

        }), 500


# ============================================================
# GET ENERGY DEMANDS
# ============================================================

@app.route(
    "/api/user_energy_demand/<int:user_id>",
    methods=["GET"]
)
def get_energy_demands(
    user_id
):

    projections = (

        EnergyDemandProjection
        .query
        .filter_by(
            user_id=
                user_id
        )
        .all()

    )


    output = []


    for projection in projections:

        stored = json.loads(
            projection
                .growth_rate
        )


        if isinstance(
            stored,
            dict
        ):

            power = stored.get(

                "power",

                stored

            )


            energy = stored.get(
                "energy"
            )


            if not isinstance(
                energy,
                dict
            ):

                energy = {

                    str(year):
                        round(
                            _safe_float(
                                value
                            )
                            * 8760
                        )

                    for (
                        year,
                        value
                    )
                    in power.items()

                }


        else:

            power = {}

            energy = {}


        output.append({

            "id":
                projection.id,

            "name":
                projection.name,

            "base_demand":
                projection.base_demand,

            "demand_per_year":
                stored,

            "energy":
                energy,

            "user_id":
                projection.user_id

        })


    return jsonify(
        output
    ), 200


# ============================================================
# DAILY PROFILE
# ============================================================

@app.route(
    "/api/daily_profile",
    methods=["POST"]
)
def save_daily_profile():

    try:

        data = (
            request.get_json()
            or {}
        )


        user_id = data[
            "user_id"
        ]


        name = str(
            data[
                "name"
            ]
        ).strip()


        hourly_values = data[
            "hourly_values"
        ]


        variability_day = _safe_float(

            data.get(
                "variability_day"
            ),

            0

        )


        variability_time = _safe_float(

            data.get(
                "variability_time"
            ),

            0

        )


        existing = (

            DailyProfile
            .query
            .filter_by(

                user_id=
                    user_id,

                name=
                    name

            )
            .first()

        )


        if existing:

            existing.hourly_values = (
                json.dumps(
                    hourly_values
                )
            )


            existing.variability_day = (
                variability_day
            )


            existing.variability_time = (
                variability_time
            )


        else:

            count = (

                DailyProfile
                .query
                .filter_by(
                    user_id=
                        user_id
                )
                .count()

            )


            if count >= 10:

                return jsonify({

                    "error":
                        "Max 10 daily profiles allowed"

                }), 400


            profile = DailyProfile(

                name=
                    name,

                hourly_values=
                    json.dumps(
                        hourly_values
                    ),

                variability_day=
                    variability_day,

                variability_time=
                    variability_time,

                user_id=
                    user_id

            )


            db.session.add(
                profile
            )


        db.session.commit()


        return jsonify({

            "message":
                "Daily profile saved"

        }), 200


    except Exception as error:

        db.session.rollback()


        traceback.print_exc()


        return jsonify({

            "error":
                "Server error",

            "details":
                str(error)

        }), 500


# ============================================================
# GET DAILY PROFILES
# ============================================================

@app.route(
    "/api/user_daily_profiles/<int:user_id>",
    methods=["GET"]
)
def get_user_profiles(
    user_id
):

    profiles = (

        DailyProfile
        .query
        .filter_by(
            user_id=
                user_id
        )
        .all()

    )


    return jsonify([

        {

            "id":
                profile.id,

            "name":
                profile.name,

            "hourly_values":
                json.loads(
                    profile
                        .hourly_values
                ),

            "variability_day":
                profile
                    .variability_day,

            "variability_time":
                profile
                    .variability_time

        }

        for profile
        in profiles

    ]), 200


# ============================================================
# GENERATE DAILY DEMAND
# ============================================================

@app.route(
    "/api/generate_demand",
    methods=["POST"]
)
def generate_demand():

    data = (
        request.get_json()
        or {}
    )


    user_id = data.get(
        "user_id"
    )


    projection_name = data.get(
        "projection_name"
    )


    profile_name = data.get(
        "profile_name"
    )


    if not all([

        user_id,
        projection_name,
        profile_name

    ]):

        return jsonify({

            "error":
                "Missing user_id, projection_name, or profile_name"

        }), 400


    projection = (

        EnergyDemandProjection
        .query
        .filter_by(

            user_id=
                user_id,

            name=
                projection_name

        )
        .first()

    )


    if not projection:

        return jsonify({

            "error":
                "Demand projection not found"

        }), 404


    profile = (

        DailyProfile
        .query
        .filter_by(

            user_id=
                user_id,

            name=
                profile_name

        )
        .first()

    )


    if not profile:

        return jsonify({

            "error":
                "Daily profile not found"

        }), 404


    try:

        hourly = json.loads(
            profile
                .hourly_values
        )


    except Exception:

        hourly = [
            1.0
        ] * 24


    if (

        not isinstance(
            hourly,
            list
        )

        or len(
            hourly
        ) != 24

    ):

        hourly = [
            1.0
        ] * 24


    variability_day = _fraction(

        profile.variability_day
        or 0

    )


    variability_time = _fraction(

        profile.variability_time
        or 0

    )


    output = []


    start_date = datetime(
        2025,
        1,
        1
    )


    for day in range(
        365
    ):

        date = (

            start_date
            + timedelta(
                days=
                    day
            )

        )


        day_modifier = random.uniform(

            1 - variability_day,

            1 + variability_day

        )


        for hour in range(
            24
        ):

            time_modifier = random.uniform(

                1 - variability_time,

                1 + variability_time

            )


            pu = (

                _safe_float(
                    hourly[
                        hour
                    ],
                    1
                )

                * day_modifier

                * time_modifier

            )


            output.append({

                "date":
                    date.strftime(
                        "%d-%b"
                    ),

                "year":
                    2025,

                "day":
                    day + 1,

                "hour":
                    hour,

                "pu":
                    round(
                        pu * 100,
                        2
                    )

            })


    return jsonify({

        "profile":
            output

    }), 200


# ============================================================
# LOCATIONS
# ============================================================

@app.route(
    "/api/locations",
    methods=["GET"]
)
def get_locations():

    locations = (
        Location
        .query
        .all()
    )


    return jsonify([

        location.to_dict()

        for location
        in locations

    ]), 200


@app.route(
    "/api/location",
    methods=["POST"]
)
def add_location():

    data = (
        request.get_json()
        or {}
    )


    try:

        location = Location(

            name=
                data[
                    "name"
                ],

            region=
                data.get(
                    "region",
                    "Durham"
                ),

            solar_irradiance=
                data[
                    "solar_irradiance"
                ],

            wind_speed=
                data[
                    "wind_speed"
                ],

            solar_profile_dry=
                data.get(
                    "solar_profile_dry"
                ),

            solar_profile_rainy=
                data.get(
                    "solar_profile_rainy"
                ),

            wind_profile_dry=
                data.get(
                    "wind_profile_dry"
                ),

            wind_profile_rainy=
                data.get(
                    "wind_profile_rainy"
                )

        )


        db.session.add(
            location
        )


        db.session.commit()


        return jsonify(
            location.to_dict()
        ), 201


    except IntegrityError:

        db.session.rollback()


        return jsonify({

            "error":
                "Location already exists"

        }), 400


    except Exception as error:

        db.session.rollback()


        traceback.print_exc()


        return jsonify({

            "error":
                "Failed to save location",

            "details":
                str(error)

        }), 500


# ============================================================
# SAVE LOCATION SIZING LIMITS
# ============================================================

@app.route(
    "/api/location_sizing_limits",
    methods=["POST"]
)
def save_location_sizing_limits():

    try:

        data = (
            request.get_json()
            or {}
        )


        user_id = data.get(
            "user_id"
        )


        location_name = str(

            data.get(
                "location_name"
            )

            or data.get(
                "region"
            )

            or ""

        ).strip()


        sources = (
            data.get(
                "sources"
            )

            or []

        )


        if not location_name:

            return jsonify({

                "error":
                    "location_name is required"

            }), 400


        if not isinstance(
            sources,
            list
        ):

            return jsonify({

                "error":
                    "sources must be a list"

            }), 400


        saved = []


        for source in sources:

            if not isinstance(
                source,
                dict
            ):

                continue


            source_id = source.get(

                "source_id",

                source.get(
                    "id"
                )

            )


            if source_id is None:

                continue


            try:

                source_id = int(
                    source_id
                )


            except (
                TypeError,
                ValueError
            ):

                continue


            source_type = str(

                source.get(
                    "type"
                )

                or source.get(
                    "technology"
                )

                or source.get(
                    "description"
                )

                or ""

            ).strip()


            if not source_type:

                continue


            limits = _normalize_sizing_limits(

                source.get(
                    "sizing_limits"
                )

                or source.get(
                    "sizingLimits"
                )

                or {}

            )


            existing = (

                LocationSizingLimit
                .query
                .filter_by(

                    location_name=
                        location_name,

                    source_id=
                        source_id

                )
                .first()

            )


            if existing:

                existing.source_type = (
                    source_type
                )


                existing.sizing_limits = (
                    json.dumps(
                        limits
                    )
                )


                if user_id:

                    existing.user_id = int(
                        user_id
                    )


            else:

                new_limit = (
                    LocationSizingLimit(

                        user_id=(

                            int(
                                user_id
                            )

                            if user_id

                            else None

                        ),

                        location_name=
                            location_name,

                        source_id=
                            source_id,

                        source_type=
                            source_type,

                        sizing_limits=
                            json.dumps(
                                limits
                            )

                    )
                )


                db.session.add(
                    new_limit
                )


            saved.append({

                "source_id":
                    source_id,

                "source_type":
                    source_type,

                "sizing_limits":
                    limits

            })


        db.session.commit()


        return jsonify({

            "message":
                f"Sizing limits saved for {location_name}",

            "location_name":
                location_name,

            "sources":
                saved

        }), 200


    except Exception as error:

        db.session.rollback()


        traceback.print_exc()


        return jsonify({

            "error":
                "Failed to save location sizing limits",

            "details":
                str(error)

        }), 500


# ============================================================
# LOAD LOCATION SIZING LIMITS
# ============================================================

@app.route(
    "/api/location_sizing_limits/<int:user_id>/<path:location_name>",
    methods=["GET"]
)
def get_location_sizing_limits(
    user_id,
    location_name
):

    try:

        saved_limits = (
            _load_location_sizing_limits(
                location_name
            )
        )


        return jsonify({

            "location_name":
                location_name,

            "limits_by_source":
                saved_limits

        }), 200


    except Exception as error:

        traceback.print_exc()


        return jsonify({

            "error":
                "Failed to load location sizing limits",

            "details":
                str(error)

        }), 500


# ============================================================
# LOAD USER DEMAND DATA
# ============================================================

def _load_user_demand_data(
    user_id
):

    projections = (

        EnergyDemandProjection
        .query
        .filter_by(
            user_id=
                user_id
        )
        .all()

    )


    output = []


    for projection in projections:

        growth_data = json.loads(
            projection
                .growth_rate
        )


        if (

            isinstance(
                growth_data,
                dict
            )

            and "energy"
                in growth_data

        ):

            energy_data = {

                str(year):
                    _safe_float(
                        value
                    )

                for (
                    year,
                    value
                )
                in growth_data
                    .get(
                        "energy",
                        {}
                    )
                    .items()

            }


        else:

            power_data = (

                growth_data.get(

                    "power",

                    growth_data

                )

                if isinstance(
                    growth_data,
                    dict
                )

                else {}

            )


            energy_data = {

                str(year):
                    round(

                        _safe_float(
                            value
                        )

                        * 8760

                    )

                for (
                    year,
                    value
                )
                in power_data.items()

            }


        output.append({

            "id":
                projection.id,

            "name":
                projection.name,

            "base_demand":
                projection.base_demand,

            "demand_per_year":
                growth_data,

            "energy":
                energy_data,

            "user_id":
                projection.user_id

        })


    return output


def _get_energy_by_projection(
    user_id,
    projection_name
):

    all_demand_data = (
        _load_user_demand_data(
            user_id
        )
    )


    matched = next(

        (

            projection

            for projection
            in all_demand_data

            if (
                projection[
                    "name"
                ]
                ==
                projection_name
            )

        ),

        None

    )


    if not matched:

        raise ValueError(

            f"Selected demand projection not found: {projection_name}"

        )


    return matched.get(
        "energy",
        {}
    )


def _get_demand_for_year(
    energy_by_year,
    year
):

    year_key = str(
        year
    )


    if year_key in (
        energy_by_year
    ):

        return _safe_float(

            energy_by_year[
                year_key
            ]

        )


    if (

        int(year) >=
        2060

        and "2060-2100"
        in energy_by_year

    ):

        return _safe_float(

            energy_by_year[
                "2060-2100"
            ]

        )


    return 0.0


# ============================================================
# CAPACITY FACTORS
# ============================================================

CAPACITY_FACTORS = {

    "Nuclear":
        0.909,

    "Geothermal":
        0.672,

    "Biomass":
        0.671,

    "Coal":
        0.589,

    "Natural Gas":
        0.503,

    "Hydro":
        0.405,

    "Wind":
        0.15,

    "Solar":
        0.12,

    "Hydrogen":
        0.60,

    "Tidal":
        0.30,

    "Thermal":
        0.80

}


# ============================================================
# AUTOMATIC SCENARIO GENERATION
# ============================================================

def _annual_cost_per_kwh(
    source,
    capacity_factor,
    discount_rate
):

    if capacity_factor <= 0:

        return float(
            "inf"
        )


    capex = _safe_float(

        source.get(
            "capital_cost"
        ),

        0

    )


    opex = _safe_float(

        source.get(
            "om_cost"
        ),

        0

    )


    fuel = _safe_float(

        source.get(
            "fuel_price"
        ),

        0

    )


    lifetime = _safe_int(

        source.get(
            "lifetime"
        ),

        25

    )


    crf = _compute_crf(

        discount_rate,
        lifetime

    )


    return (

        (
            (
                capex
                * crf
            )

            + opex
        )

        /
        (
            capacity_factor
            * 8760
        )

        + fuel

    )


def _random_mix(
    number_of_sources,
    seed_value
):

    rng = random.Random(
        seed_value
    )


    if (
        number_of_sources
        <= 0
    ):

        return []


    weights = [

        rng.random()

        for _
        in range(
            number_of_sources
        )

    ]


    total = (
        sum(weights)
        or 1.0
    )


    return [

        (
            weight
            / total
        )
        * 100.0

        for weight
        in weights

    ]


def _smooth_mix(
    previous_mix,
    current_mix,
    max_delta=20
):

    if not previous_mix:

        return current_mix


    capped = []


    for (
        previous,
        current
    ) in zip(

        previous_mix,
        current_mix

    ):

        minimum = max(

            0,

            previous
            - max_delta

        )


        maximum = min(

            100,

            previous
            + max_delta

        )


        capped.append(

            min(

                max(
                    current,
                    minimum
                ),

                maximum

            )

        )


    total = (
        sum(capped)
        or 1
    )


    return [

        (
            value
            / total
        )
        * 100

        for value
        in capped

    ]


def _score_mix(
    mixes_by_year,
    sources
):

    source_costs = []


    for source in sources:

        source_type = (

            source.get(
                "type"
            )

            or source.get(
                "technology"
            )

            or ""

        )


        cf = CAPACITY_FACTORS.get(

            source_type,
            0

        )


        source_costs.append(

            _annual_cost_per_kwh(

                source,
                cf,
                0.03

            )

        )


    scores = []


    for mix in (
        mixes_by_year.values()
    ):

        score = 0


        for (
            index,
            percentage
        ) in enumerate(
            mix
        ):

            cost = source_costs[
                index
            ]


            if cost == float(
                "inf"
            ):

                cost = 1000000


            score += (

                (
                    percentage
                    / 100
                )

                * cost

            )


        scores.append(
            score
        )


    if not scores:

        return float(
            "inf"
        )


    return (

        sum(scores)
        / len(scores)

    )


def generate_best_scenarios(
    sources,
    start_year=2025,
    end_year=2100,
    number_of_candidates=150,
    top_k=5,
    seed=42
):

    years = _simulation_years(

        start_year,
        end_year

    )


    number_of_sources = len(
        sources
    )


    if number_of_sources == 0:

        return {}


    candidates = []


    for candidate_index in range(

        number_of_candidates

    ):

        mixes_by_year = {}

        previous_mix = []


        for year in years:

            mix = _random_mix(

                number_of_sources,

                seed
                + candidate_index
                + year

            )


            if previous_mix:

                mix = _smooth_mix(

                    previous_mix,
                    mix

                )


            mixes_by_year[
                year
            ] = mix


            previous_mix = mix


        score = _score_mix(

            mixes_by_year,
            sources

        )


        candidates.append(

            (
                score,
                mixes_by_year
            )

        )


    candidates.sort(

        key=lambda item:
            item[0]

    )


    best = candidates[
        :top_k
    ]


    output = {

        str(year):
            {}

        for year
        in years

    }


    for (

        option_index,
        (
            _,
            mixes
        )

    ) in enumerate(

        best,
        start=1

    ):


        for (
            year,
            mix
        ) in mixes.items():


            output[
                str(year)
            ][
                str(
                    option_index
                )
            ] = [

                round(
                    value,
                    4
                )

                for value
                in mix

            ]


    return output


# ============================================================
# ELECTRICITY SIMULATION
# ============================================================

def _run_electricity_simulation(
    data
):

    user_id = int(
        data[
            "user_id"
        ]
    )


    sources = (
        data.get(
            "sources"
        )

        or []

    )


    if not sources:

        raise ValueError(
            "At least one source is required"
        )


    run_mode = str(

        data.get(
            "run_mode",
            "single"
        )

    ).lower()


    active_region = str(

        data.get(
            "region"
        )

        or "Region"

    )


    selected_regions = (

        data.get(
            "selected_regions"
        )

        or [
            active_region
        ]

    )


    start_year = _safe_int(

        data.get(
            "start_year"
        ),

        2025

    )


    end_year = _safe_int(

        data.get(
            "end_year"
        ),

        2100

    )


    projection_name = str(

        data.get(
            "projection_name"
        )

        or ""

    )


    projections_by_region = (

        data.get(
            "projections_by_region"
        )

        or {}

    )


    transmission_limits = (

        data.get(
            "transmission_limit"
        )

        or {}

    )


    transmission_loss = _safe_float(

        data.get(
            "transmission_loss"
        ),

        0.05

    )


    use_custom_mix = bool(

        data.get(
            "use_custom_mix",
            False
        )

    )


    custom_caps = (

        data.get(
            "custom_installed_capacities"
        )

        or {}

    )


    for source in sources:

        source[
            "sizing_limits"
        ] = (

            source.get(
                "sizing_limits"
            )

            or source.get(
                "sizingLimits"
            )

            or {}

        )


    if use_custom_mix:

        installed_capacities = {}


        for (
            year,
            percentages
        ) in custom_caps.items():


            installed_capacities[
                str(year)
            ] = {

                "1": [

                    _safe_float(
                        value
                    )

                    for value
                    in percentages

                ]

            }


    else:

        installed_capacities = (
            generate_best_scenarios(

                sources=
                    sources,

                start_year=
                    start_year,

                end_year=
                    end_year

            )
        )


    all_demand_data = (
        _load_user_demand_data(
            user_id
        )
    )


    def simulate_region(
        region_name
    ):

        region_projection_name = (

            projections_by_region.get(

                region_name,

                projection_name

            )

        )


        matched_projection = next(

            (

                projection

                for projection
                in all_demand_data

                if (
                    projection[
                        "name"
                    ]
                    ==
                    region_projection_name
                )

            ),

            None

        )


        if not matched_projection:

            raise ValueError(

                f"Selected demand projection not found for region {region_name}"

            )


        energy_by_year = (
            matched_projection.get(
                "energy",
                {}
            )
        )


        results = []


        energy_options = defaultdict(

            lambda:
                defaultdict(
                    dict
                )

        )


        for (

            year_str,
            option_sets

        ) in installed_capacities.items():


            year = int(
                year_str
            )


            if not (

                start_year
                <= year
                <= end_year

            ):

                continue


            demand_mwh = _get_demand_for_year(

                energy_by_year,
                year

            )


            for (

                option_str,
                capacity_row

            ) in option_sets.items():


                option_index = int(
                    option_str
                )


                total_annual_cost = 0

                total_energy_kwh = 0


                for (

                    source_index,
                    share_percent

                ) in enumerate(
                    capacity_row
                ):


                    if source_index >= len(
                        sources
                    ):

                        continue


                    if share_percent <= 0:

                        continue


                    source = sources[
                        source_index
                    ]


                    source_type = str(

                        source.get(
                            "type"
                        )

                        or ""

                    )


                    source_id = source.get(

                        "id",

                        source_index + 1

                    )


                    capacity_factor = (

                        CAPACITY_FACTORS.get(

                            source_type,
                            0

                        )

                    )


                    if capacity_factor <= 0:

                        continue


                    fallback_limit = _safe_float(

                        source.get(
                            "sizing_limits",
                            {}
                        ).get(
                            year_str
                        ),

                        0

                    )


                    sizing_limit_gw = (

                        _get_region_sizing_limit(

                            location_name=
                                region_name,

                            source_id=
                                source_id,

                            year=
                                year_str,

                            fallback=
                                fallback_limit

                        )

                    )


                    derating = _safe_float(

                        source.get(
                            "derating_factor"
                        ),

                        1

                    )


                    scaling = _safe_float(

                        source.get(
                            "scaling_factor"
                        ),

                        1

                    )


                    reliability_margin = (
                        0.8
                    )


                    requested_energy_mwh = (

                        demand_mwh

                        * (
                            share_percent
                            / 100
                        )

                    )


                    # =================================================
                    # SIZING LIMIT NOW ACTUALLY LIMITS GENERATION
                    #
                    # GW × 1000 = MW
                    # MW × CF × 8760 = MWh/year
                    # =================================================

                    max_energy_mwh = (

                        max(
                            sizing_limit_gw,
                            0
                        )

                        * 1000

                        * capacity_factor

                        * 8760

                        * derating

                        * scaling

                        * reliability_margin

                    )


                    actual_energy_mwh = min(

                        requested_energy_mwh,

                        max_energy_mwh

                    )


                    energy_generated_gwh = (

                        actual_energy_mwh
                        / 1000

                    )


                    required_capacity_kw = (

                        (
                            actual_energy_mwh
                            * 1000
                        )

                        /
                        (
                            capacity_factor
                            * 8760
                        )

                        if capacity_factor > 0

                        else 0

                    )


                    capex = _safe_float(

                        source.get(
                            "capital_cost"
                        ),

                        0

                    )


                    opex = _safe_float(

                        source.get(
                            "om_cost"
                        ),

                        0

                    )


                    fuel_price = _safe_float(

                        source.get(
                            "fuel_price"
                        ),

                        0

                    )


                    lifetime = _safe_int(

                        source.get(
                            "lifetime"
                        ),

                        25

                    )


                    crf = _compute_crf(

                        0.03,
                        lifetime

                    )


                    annualized_capital = (

                        required_capacity_kw
                        * capex
                        * crf

                    )


                    annual_om = (

                        required_capacity_kw
                        * opex

                    )


                    annual_fuel = (

                        actual_energy_mwh

                        * 1000

                        * fuel_price

                    )


                    annual_total_cost = (

                        annualized_capital

                        + annual_om

                        + annual_fuel

                    )


                    total_annual_cost += (
                        annual_total_cost
                    )


                    total_energy_kwh += (

                        actual_energy_mwh
                        * 1000

                    )


                    percent = (

                        (
                            actual_energy_mwh
                            / demand_mwh
                        )
                        * 100

                        if demand_mwh > 0

                        else 0

                    )


                    results.append({

                        "user_id":
                            user_id,

                        "region":
                            region_name,

                        "option":
                            option_index,

                        "year":
                            year,

                        "demand":
                            round(
                                demand_mwh,
                                3
                            ),

                        "apple":
                            round(
                                demand_mwh,
                                3
                            ),

                        "source_index":
                            source_index + 1,

                        "source_id":
                            source_id,

                        "source_type":
                            source_type,

                        "sizing_limit_gw":
                            round(
                                sizing_limit_gw,
                                6
                            ),

                        "requested_share_percent":
                            round(
                                share_percent,
                                4
                            ),

                        "energy_generated":
                            round(
                                energy_generated_gwh,
                                4
                            ),

                        "energy_generated_gwh":
                            round(
                                energy_generated_gwh,
                                4
                            ),

                        # Used by economic analysis.
                        # This is MWh.
                        "financial_energy_generated":
                            round(
                                actual_energy_mwh,
                                3
                            ),

                        "required_capacity_kw":
                            round(
                                required_capacity_kw,
                                3
                            ),

                        "percent":
                            round(
                                percent,
                                2
                            ),

                        "annual_total_cost":
                            round(
                                annual_total_cost,
                                2
                            )

                    })


                    option_key = (
                        f"Option {option_index}"
                    )


                    # =================================================
                    # ADD SAME TECHNOLOGIES TOGETHER
                    # rather than overwrite them.
                    # =================================================

                    previous_energy = (

                        energy_options[
                            year_str
                        ][
                            option_key
                        ].get(

                            source_type,

                            0

                        )

                    )


                    energy_options[
                        year_str
                    ][
                        option_key
                    ][
                        source_type
                    ] = round(

                        previous_energy
                        + energy_generated_gwh,

                        4

                    )


                option_key = (
                    f"Option {option_index}"
                )


                coe = (

                    total_annual_cost
                    / total_energy_kwh

                    if total_energy_kwh > 0

                    else 0

                )


                energy_options[
                    year_str
                ][
                    option_key
                ][
                    "COE"
                ] = round(
                    coe,
                    6
                )


        return (

            results,
            energy_options,
            energy_by_year

        )


    # ============================================================
    # MULTI-LOCATION
    # ============================================================

    if run_mode == "multi":

        regions = (

            selected_regions
            or [
                active_region
            ]

        )


        results_by_region = {}

        all_results = []


        aggregated_options = defaultdict(

            lambda:
                defaultdict(
                    dict
                )

        )


        region_balances = {}


        for region in regions:

            (

                region_results,
                region_options,
                energy_by_year

            ) = simulate_region(
                region
            )


            results_by_region[
                region
            ] = {

                "results":
                    region_results,

                "energy_options":
                    region_options

            }


            all_results.extend(
                region_results
            )


            region_balances[
                region
            ] = {}


            for year in _simulation_years(

                start_year,
                end_year

            ):

                year_str = str(
                    year
                )


                demand_mwh = (

                    _get_demand_for_year(

                        energy_by_year,
                        year

                    )

                )


                option_one_rows = [

                    row

                    for row
                    in region_results

                    if (

                        row[
                            "year"
                        ]
                        ==
                        year

                        and row[
                            "option"
                        ]
                        ==
                        1

                    )

                ]


                generation_gwh = sum(

                    row.get(
                        "energy_generated_gwh",
                        0
                    )

                    for row
                    in option_one_rows

                )


                demand_gwh = (

                    demand_mwh
                    / 1000

                )


                region_balances[
                    region
                ][
                    year_str
                ] = round(

                    generation_gwh
                    - demand_gwh,

                    4

                )


            for (

                year,
                options

            ) in region_options.items():


                for (

                    option,
                    values

                ) in options.items():


                    for (

                        key,
                        value

                    ) in values.items():


                        if key == "COE":

                            aggregated_options[
                                year
                            ][
                                option
                            ].setdefault(

                                "COE_list",
                                []

                            ).append(
                                value
                            )


                        else:

                            aggregated_options[
                                year
                            ][
                                option
                            ][
                                key
                            ] = (

                                aggregated_options[
                                    year
                                ][
                                    option
                                ].get(
                                    key,
                                    0
                                )

                                + value

                            )


        for year in aggregated_options:

            for option in (
                aggregated_options[
                    year
                ]
            ):

                coe_list = (

                    aggregated_options[
                        year
                    ][
                        option
                    ].pop(

                        "COE_list",
                        []

                    )

                )


                aggregated_options[
                    year
                ][
                    option
                ][
                    "COE"
                ] = (

                    round(

                        sum(
                            coe_list
                        )
                        /
                        len(
                            coe_list
                        ),

                        6

                    )

                    if coe_list

                    else 0

                )


        # ========================================================
        # ENERGY SHARING
        # ========================================================

        energy_sharing = []


        for year in _simulation_years(

            start_year,
            end_year

        ):

            year_str = str(
                year
            )


            for from_region in regions:

                surplus = max(

                    region_balances
                    .get(
                        from_region,
                        {}
                    )
                    .get(
                        year_str,
                        0
                    ),

                    0

                )


                if surplus <= 0:

                    continue


                for to_region in regions:

                    if (
                        from_region
                        ==
                        to_region
                    ):

                        continue


                    deficit = max(

                        -region_balances
                        .get(
                            to_region,
                            {}
                        )
                        .get(
                            year_str,
                            0
                        ),

                        0

                    )


                    if deficit <= 0:

                        continue


                    pair_key = (
                        f"{from_region}-{to_region}"
                    )


                    limit_value = (

                        transmission_limits
                        .get(
                            pair_key,
                            {}
                        )
                        .get(
                            year_str,
                            100
                        )

                    )


                    transfer_limit = _safe_float(

                        limit_value,
                        100

                    )


                    sent = min(

                        surplus,
                        deficit,
                        transfer_limit

                    )


                    received = (

                        sent
                        * (
                            1
                            - transmission_loss
                        )

                    )


                    energy_sharing.append({

                        "year":
                            year,

                        "from":
                            from_region,

                        "to":
                            to_region,

                        "sent":
                            round(
                                sent,
                                4
                            ),

                        "received":
                            round(
                                received,
                                4
                            ),

                        "loss":
                            round(

                                sent
                                - received,

                                4

                            )

                    })


                    region_balances[
                        from_region
                    ][
                        year_str
                    ] -= sent


                    region_balances[
                        to_region
                    ][
                        year_str
                    ] += received


                    surplus -= sent


                    if surplus <= 0:

                        break


        return {

            "simulation_type":
                "electric",

            "selected_regions":
                regions,

            "results":
                all_results,

            "results_by_region":
                results_by_region,

            "aggregated": {

                "energy_options":
                    aggregated_options

            },

            "energy_sharing":
                energy_sharing,

            "region_balances":
                region_balances

        }


    # ============================================================
    # SINGLE LOCATION
    # ============================================================

    (
        region_results,
        energy_options,
        _
    ) = simulate_region(
        active_region
    )


    return {

        "simulation_type":
            "electric",

        "selected_regions":
            [
                active_region
            ],

        "results":
            region_results,

        "energy_options":
            energy_options

    }


# ============================================================
# HYDROGEN COST HELPER
# ============================================================

def _annual_cost_and_coe(
    capacity_gw,
    energy_gwh,
    source=None,
    fuel_price_override=None
):

    source = (
        source
        or {}
    )


    capacity_kw = (

        _safe_float(
            capacity_gw
        )

        * 1_000_000

    )


    energy_kwh = (

        _safe_float(
            energy_gwh
        )

        * 1_000_000

    )


    capex = _safe_float(

        source.get(
            "capital_cost"
        ),

        0

    )


    opex = _safe_float(

        source.get(
            "om_cost"
        ),

        0

    )


    fuel_price = _safe_float(

        (
            fuel_price_override

            if (
                fuel_price_override
                is not None
            )

            else source.get(
                "fuel_price"
            )
        ),

        0

    )


    lifetime = _safe_int(

        source.get(
            "lifetime"
        ),

        25

    )


    crf = _compute_crf(

        0.03,
        lifetime

    )


    annual_capital = (

        capacity_kw
        * capex
        * crf

    )


    annual_om = (

        capacity_kw
        * opex

    )


    annual_fuel = (

        energy_kwh
        * fuel_price

    )


    annual_total_cost = (

        annual_capital
        + annual_om
        + annual_fuel

    )


    coe = (

        annual_total_cost
        / energy_kwh

        if energy_kwh > 0

        else 0

    )


    return (

        annual_total_cost,
        coe

    )


# ============================================================
# HYDROGEN SIMULATION
# ============================================================

def _run_hydrogen_simulation(
    data
):

    user_id = int(
        data[
            "user_id"
        ]
    )


    sources = (

        data.get(
            "sources"
        )

        or []

    )


    start_year = _safe_int(

        data.get(
            "start_year"
        ),

        2025

    )


    end_year = _safe_int(

        data.get(
            "end_year"
        ),

        2100

    )


    run_mode = str(

        data.get(
            "run_mode",
            "single"
        )

    ).lower()


    active_region = str(

        data.get(
            "region"
        )

        or "Region"

    )


    selected_regions = (

        data.get(
            "selected_regions"
        )

        or [
            active_region
        ]

    )


    default_projection_name = str(

        data.get(
            "projection_name"
        )

        or ""

    )


    projections_by_region = (

        data.get(
            "projections_by_region"
        )

        or {}

    )


    hydrogen_params = (

        data.get(
            "hydrogen_params"
        )

        or {}

    )


    hydrogen_source = (
        _find_source_by_type(

            sources,
            "Hydrogen"

        )
    )


    if hydrogen_source is None:

        hydrogen_source = {

            "type":
                "Hydrogen",

            "description":
                "Hydrogen",

            "capital_cost":
                _safe_float(

                    hydrogen_params.get(
                        "capital_cost"
                    ),

                    1200

                ),

            "om_cost":
                _safe_float(

                    hydrogen_params.get(
                        "om_cost"
                    ),

                    0.05

                ),

            "fuel_price":
                0,

            "lifetime":
                _safe_int(

                    hydrogen_params.get(
                        "lifetime"
                    ),

                    20

                )

        }


    electrolyzer_capacity_gw = _safe_float(

        hydrogen_params.get(
            "electrolyzer_capacity_gw"
        ),

        0.005

    )


    electrolyzer_efficiency = _safe_float(

        hydrogen_params.get(
            "electrolyzer_efficiency"
        ),

        0.70

    )


    external_electricity_gwh = _safe_float(

        hydrogen_params.get(
            "external_electricity_to_electrolyzer_gwh"
        ),

        0

    )


    hydrogen_storage_capacity_kg = _safe_float(

        hydrogen_params.get(
            "hydrogen_storage_capacity_kg"
        ),

        1000

    )


    initial_hydrogen_kg = _safe_float(

        hydrogen_params.get(
            "initial_hydrogen_kg"
        ),

        0

    )


    storage_loss = _fraction(

        hydrogen_params.get(
            "storage_loss"
        ),

        0.02

    )


    fuel_cell_capacity_gw = _safe_float(

        hydrogen_params.get(
            "fuel_cell_capacity_gw"
        ),

        0.003

    )


    fuel_cell_efficiency = _safe_float(

        hydrogen_params.get(
            "fuel_cell_efficiency"
        ),

        0.55

    )


    pipeline_length_km = _safe_float(

        hydrogen_params.get(
            "pipeline_length_km"
        ),

        2

    )


    pipeline_loss_percent = _safe_float(

        hydrogen_params.get(
            "pipeline_loss_percent"
        ),

        1.5

    )


    pipeline_loss_fraction = (

        pipeline_loss_percent
        / 100

    )


    pipeline_cost_per_km = _safe_float(

        hydrogen_params.get(
            "pipeline_cost_per_km"
        ),

        100000

    )


    pipeline_om_cost_per_km_year = _safe_float(

        hydrogen_params.get(
            "pipeline_om_cost_per_km_year"
        ),

        2000

    )


    h2_lhv_kwh_per_kg = (
        33.33
    )


    years = _simulation_years(

        start_year,
        end_year

    )


    # ============================================================
    # EXISTING ELECTRIC GENERATION
    # ============================================================

    def calculate_existing_generation_gwh(
        year,
        region_name
    ):

        total = 0


        for source in sources:

            source_type = str(

                source.get(
                    "type"
                )

                or source.get(
                    "technology"
                )

                or ""

            )


            if source_type in [

                "Hydrogen",
                "Thermal"

            ]:

                continue


            capacity_factor = (

                CAPACITY_FACTORS.get(

                    source_type,
                    0

                )

            )


            capacity_gw = (
                _get_source_capacity_for_year(

                    source,
                    year,
                    region_name

                )
            )


            total += (

                capacity_gw
                * capacity_factor
                * 8760

            )


        return total


    def simulate_region(
        region_name
    ):

        projection_name = (

            projections_by_region.get(

                region_name,

                default_projection_name

            )

        )


        energy_by_year = (
            _get_energy_by_projection(

                user_id,
                projection_name

            )
        )


        results = []


        energy_options = defaultdict(

            lambda:
                defaultdict(
                    dict
                )

        )


        stored_hydrogen_kg = min(

            initial_hydrogen_kg,

            hydrogen_storage_capacity_kg

        )


        for year in years:

            demand_gwh = (

                _get_demand_for_year(

                    energy_by_year,
                    year

                )

                / 1000

            )


            existing_generation_gwh = (

                calculate_existing_generation_gwh(

                    year,
                    region_name

                )

            )


            electric_surplus_gwh = max(

                existing_generation_gwh
                - demand_gwh,

                0

            )


            electric_deficit_gwh = max(

                demand_gwh
                - existing_generation_gwh,

                0

            )


            # ========================================================
            # ELECTROLYZER
            # ========================================================

            max_electrolyzer_input_gwh = (

                electrolyzer_capacity_gw
                * 8760

            )


            electricity_from_surplus_gwh = min(

                electric_surplus_gwh,

                max_electrolyzer_input_gwh

            )


            remaining_electrolyzer_capacity_gwh = max(

                max_electrolyzer_input_gwh
                - electricity_from_surplus_gwh,

                0

            )


            electricity_from_external_gwh = min(

                external_electricity_gwh,

                remaining_electrolyzer_capacity_gwh

            )


            electricity_to_electrolyzer_gwh = (

                electricity_from_surplus_gwh

                + electricity_from_external_gwh

            )


            hydrogen_produced_kg = (

                electricity_to_electrolyzer_gwh

                * 1_000_000

                * electrolyzer_efficiency

            ) / h2_lhv_kwh_per_kg


            # ========================================================
            # PIPELINE
            # ========================================================

            pipeline_loss_kg = (

                hydrogen_produced_kg

                * pipeline_loss_fraction

            )


            hydrogen_after_pipeline_kg = (

                hydrogen_produced_kg

                - pipeline_loss_kg

            )


            # ========================================================
            # STORAGE
            # ========================================================

            stored_hydrogen_kg += (
                hydrogen_after_pipeline_kg
            )


            storage_loss_kg = (

                stored_hydrogen_kg

                * storage_loss

            )


            stored_hydrogen_kg -= (
                storage_loss_kg
            )


            hydrogen_spilled_kg = max(

                stored_hydrogen_kg

                - hydrogen_storage_capacity_kg,

                0

            )


            stored_hydrogen_kg = min(

                stored_hydrogen_kg,

                hydrogen_storage_capacity_kg

            )


            # ========================================================
            # FUEL CELL
            # ========================================================

            max_fuel_cell_output_gwh = (

                fuel_cell_capacity_gw

                * 8760

            )


            target_fuel_cell_output_gwh = min(

                electric_deficit_gwh,

                max_fuel_cell_output_gwh

            )


            hydrogen_needed_kg = (

                (
                    target_fuel_cell_output_gwh
                    * 1_000_000
                )

                /
                (
                    h2_lhv_kwh_per_kg

                    * fuel_cell_efficiency
                )

                if fuel_cell_efficiency > 0

                else 0

            )


            hydrogen_used_kg = min(

                stored_hydrogen_kg,

                hydrogen_needed_kg

            )


            fuel_cell_output_gwh = (

                hydrogen_used_kg

                * h2_lhv_kwh_per_kg

                * fuel_cell_efficiency

            ) / 1_000_000


            stored_hydrogen_kg = max(

                stored_hydrogen_kg

                - hydrogen_used_kg,

                0

            )


            final_unmet_demand_gwh = max(

                electric_deficit_gwh

                - fuel_cell_output_gwh,

                0

            )


            remaining_surplus_gwh = max(

                electric_surplus_gwh

                - electricity_from_surplus_gwh,

                0

            )


            # ========================================================
            # COST
            # ========================================================

            (

                annual_cost,
                _

            ) = _annual_cost_and_coe(

                electrolyzer_capacity_gw
                + fuel_cell_capacity_gw,

                fuel_cell_output_gwh,

                hydrogen_source,

                fuel_price_override=
                    0

            )


            pipeline_capital_cost = (

                pipeline_length_km

                * pipeline_cost_per_km

            )


            pipeline_annualized_cost = (

                pipeline_capital_cost

                * _compute_crf(

                    0.03,

                    _safe_int(

                        hydrogen_source.get(
                            "lifetime"
                        ),

                        20

                    )

                )

            )


            pipeline_annual_om = (

                pipeline_length_km

                * pipeline_om_cost_per_km_year

            )


            annual_total_cost = (

                annual_cost

                + pipeline_annualized_cost

                + pipeline_annual_om

            )


            coe = (

                annual_total_cost

                /
                (
                    fuel_cell_output_gwh
                    * 1_000_000
                )

                if fuel_cell_output_gwh > 0

                else 0

            )


            row = {

                "user_id":
                    user_id,

                "region":
                    region_name,

                "option":
                    1,

                "year":
                    year,

                "source_index":
                    1,

                "source_type":
                    "Hydrogen",

                "demand":
                    round(
                        demand_gwh,
                        3
                    ),

                "apple":
                    round(
                        demand_gwh,
                        3
                    ),

                "existing_electric_generation_gwh":
                    round(
                        existing_generation_gwh,
                        3
                    ),

                "electric_surplus_gwh":
                    round(
                        electric_surplus_gwh,
                        3
                    ),

                "electric_deficit_gwh":
                    round(
                        electric_deficit_gwh,
                        3
                    ),

                "electricity_to_electrolyzer_gwh":
                    round(
                        electricity_to_electrolyzer_gwh,
                        3
                    ),

                "hydrogen_produced_kg":
                    round(
                        hydrogen_produced_kg,
                        3
                    ),

                "hydrogen_pipeline_loss_kg":
                    round(
                        pipeline_loss_kg,
                        3
                    ),

                "hydrogen_stored_kg":
                    round(
                        stored_hydrogen_kg,
                        3
                    ),

                "hydrogen_spilled_kg":
                    round(
                        hydrogen_spilled_kg,
                        3
                    ),

                "storage_loss_kg":
                    round(
                        storage_loss_kg,
                        3
                    ),

                "hydrogen_used_kg":
                    round(
                        hydrogen_used_kg,
                        3
                    ),

                "fuel_cell_output_gwh":
                    round(
                        fuel_cell_output_gwh,
                        3
                    ),

                "energy_generated":
                    round(
                        fuel_cell_output_gwh,
                        3
                    ),

                "surplus":
                    round(
                        remaining_surplus_gwh,
                        3
                    ),

                "unmet_demand":
                    round(
                        final_unmet_demand_gwh,
                        3
                    ),

                "annual_total_cost":
                    round(
                        annual_total_cost,
                        2
                    ),

                "coe":
                    round(
                        coe,
                        6
                    )

            }


            results.append(
                row
            )


            energy_options[
                str(year)
            ][
                "Option 1"
            ][
                "Hydrogen"
            ] = round(

                fuel_cell_output_gwh,
                3

            )


            energy_options[
                str(year)
            ][
                "Option 1"
            ][
                "COE"
            ] = round(
                coe,
                6
            )


        return (

            results,
            energy_options

        )


    # ============================================================
    # HYDROGEN MULTI-LOCATION
    # ============================================================

    if run_mode == "multi":

        regions = (

            selected_regions

            or [
                active_region
            ]

        )


        all_results = []

        results_by_region = {}


        aggregated_options = defaultdict(

            lambda:
                defaultdict(
                    dict
                )

        )


        for region in regions:

            (

                rows,
                options

            ) = simulate_region(
                region
            )


            all_results.extend(
                rows
            )


            results_by_region[
                region
            ] = {

                "results":
                    rows,

                "energy_options":
                    options

            }


            for (

                year,
                option_values

            ) in options.items():


                for (

                    option,
                    values

                ) in option_values.items():


                    for (

                        key,
                        value

                    ) in values.items():


                        if key == "COE":

                            aggregated_options[
                                year
                            ][
                                option
                            ].setdefault(

                                "COE_list",
                                []

                            ).append(
                                value
                            )


                        else:

                            aggregated_options[
                                year
                            ][
                                option
                            ][
                                key
                            ] = (

                                aggregated_options[
                                    year
                                ][
                                    option
                                ].get(
                                    key,
                                    0
                                )

                                + value

                            )


        for year in aggregated_options:

            for option in (
                aggregated_options[
                    year
                ]
            ):

                coe_list = (

                    aggregated_options[
                        year
                    ][
                        option
                    ].pop(

                        "COE_list",
                        []

                    )

                )


                aggregated_options[
                    year
                ][
                    option
                ][
                    "COE"
                ] = (

                    round(

                        sum(
                            coe_list
                        )
                        /
                        len(
                            coe_list
                        ),

                        6

                    )

                    if coe_list

                    else 0

                )


        return {

            "simulation_type":
                "hydrogen",

            "selected_regions":
                regions,

            "results":
                all_results,

            "results_by_region":
                results_by_region,

            "aggregated": {

                "energy_options":
                    aggregated_options

            }

        }


    rows, options = (
        simulate_region(
            active_region
        )
    )


    return {

        "simulation_type":
            "hydrogen",

        "selected_regions":
            [
                active_region
            ],

        "results":
            rows,

        "energy_options":
            options

    }


# ============================================================
# THERMAL SIMULATION
# ============================================================

def _run_thermal_simulation(
    data
):

    user_id = int(
        data[
            "user_id"
        ]
    )


    sources = (

        data.get(
            "sources"
        )

        or []

    )


    thermal_params = (

        data.get(
            "thermal_params"
        )

        or {}

    )


    inflation = (

        data.get(
            "inflation"
        )

        or {}

    )


    start_year = _safe_int(

        data.get(
            "start_year"
        ),

        2025

    )


    end_year = _safe_int(

        data.get(
            "end_year"
        ),

        2100

    )


    years = _simulation_years(

        start_year,
        end_year

    )


    run_mode = str(

        data.get(
            "run_mode",
            "single"
        )

    ).lower()


    active_region = str(

        data.get(
            "region"
        )

        or "Region"

    )


    selected_regions = (

        data.get(
            "selected_regions"
        )

        or [
            active_region
        ]

    )


    default_projection_name = str(

        data.get(
            "projection_name"
        )

        or ""

    )


    projections_by_region = (

        data.get(
            "projections_by_region"
        )

        or {}

    )


    thermal_capacity_gw = _safe_float(

        thermal_params.get(
            "thermal_capacity_gw"
        ),

        0

    )


    capacity_factor = _safe_float(

        thermal_params.get(
            "capacity_factor"
        ),

        0.80

    )


    thermal_efficiency = _safe_float(

        thermal_params.get(
            "thermal_efficiency"
        ),

        0.85

    )


    fuel_type = str(

        thermal_params.get(
            "fuel_type"
        )

        or "Natural Gas"

    )


    fuel_price = _safe_float(

        thermal_params.get(
            "fuel_price"
        ),

        0.30

    )


    base_thermal_load_gwh = _safe_float(

        thermal_params.get(
            "annual_thermal_load_gwh"
        ),

        0

    )


    storage_capacity_gwh = _safe_float(

        thermal_params.get(
            "storage_capacity_gwh"
        ),

        0

    )


    initial_storage_gwh = _safe_float(

        thermal_params.get(
            "initial_storage_gwh"
        ),

        0

    )


    storage_loss = _fraction(

        thermal_params.get(
            "storage_loss"
        ),

        0.05

    )


    storage_discharge_efficiency = _safe_float(

        thermal_params.get(
            "storage_discharge_efficiency"
        ),

        0.90

    )


    thermal_source = (

        _find_source_by_type(
            sources,
            "Thermal"
        )

        or _find_source_by_type(
            sources,
            fuel_type
        )

        or {}

    )


    def simulate_region(
        region_name
    ):

        projection_name = (

            projections_by_region.get(

                region_name,

                default_projection_name

            )

        )


        energy_by_year = {}

        base_projection_demand = 0


        if projection_name:

            try:

                energy_by_year = (
                    _get_energy_by_projection(

                        user_id,
                        projection_name

                    )
                )


                if years:

                    base_projection_demand = (

                        _get_demand_for_year(

                            energy_by_year,

                            years[0]

                        )

                    )


            except Exception:

                energy_by_year = {}

                base_projection_demand = 0


        stored_heat_gwh = min(

            initial_storage_gwh,

            storage_capacity_gwh

        )


        rows = []


        energy_options = defaultdict(

            lambda:
                defaultdict(
                    dict
                )

        )


        for year in years:

            # ========================================================
            # LOAD
            # ========================================================

            if base_thermal_load_gwh > 0:

                if base_projection_demand > 0:

                    year_projection_demand = (

                        _get_demand_for_year(

                            energy_by_year,
                            year

                        )

                    )


                    load_multiplier = (

                        year_projection_demand
                        / base_projection_demand

                        if year_projection_demand > 0

                        else 1

                    )


                else:

                    load_multiplier = 1


                thermal_load_gwh = (

                    base_thermal_load_gwh

                    * load_multiplier

                )


            else:

                thermal_load_gwh = 0


            # ========================================================
            # THERMAL GENERATION
            # GW × 8760 = GWh/year
            # ========================================================

            gross_heat_gwh = (

                thermal_capacity_gw

                * capacity_factor

                * 8760

            )


            useful_heat_generation_gwh = (

                gross_heat_gwh

                * thermal_efficiency

            )


            # ========================================================
            # STORAGE LOSS
            # ========================================================

            storage_loss_gwh = (

                stored_heat_gwh

                * storage_loss

            )


            stored_heat_gwh = max(

                stored_heat_gwh

                - storage_loss_gwh,

                0

            )


            storage_charged_gwh = 0

            storage_discharged_gwh = 0

            thermal_surplus_gwh = 0

            unmet_thermal_gwh = 0


            # ========================================================
            # BALANCE
            # ========================================================

            if (

                useful_heat_generation_gwh
                >=
                thermal_load_gwh

            ):

                thermal_served_gwh = (
                    thermal_load_gwh
                )


                extra_heat_gwh = (

                    useful_heat_generation_gwh

                    - thermal_load_gwh

                )


                available_storage_room_gwh = max(

                    storage_capacity_gwh

                    - stored_heat_gwh,

                    0

                )


                storage_charged_gwh = min(

                    extra_heat_gwh,

                    available_storage_room_gwh

                )


                stored_heat_gwh += (
                    storage_charged_gwh
                )


                thermal_surplus_gwh = max(

                    extra_heat_gwh

                    - storage_charged_gwh,

                    0

                )


            else:

                direct_served_gwh = (
                    useful_heat_generation_gwh
                )


                remaining_load_gwh = (

                    thermal_load_gwh

                    - direct_served_gwh

                )


                possible_storage_output_gwh = (

                    stored_heat_gwh

                    * storage_discharge_efficiency

                )


                storage_discharged_gwh = min(

                    remaining_load_gwh,

                    possible_storage_output_gwh

                )


                if (

                    storage_discharge_efficiency
                    > 0

                ):

                    stored_heat_gwh -= (

                        storage_discharged_gwh

                        / storage_discharge_efficiency

                    )


                stored_heat_gwh = max(

                    stored_heat_gwh,
                    0

                )


                thermal_served_gwh = (

                    direct_served_gwh

                    + storage_discharged_gwh

                )


                unmet_thermal_gwh = max(

                    thermal_load_gwh

                    - thermal_served_gwh,

                    0

                )


            # ========================================================
            # COST
            # ========================================================

            capacity_kw = (

                thermal_capacity_gw

                * 1_000_000

            )


            served_heat_kwh = (

                thermal_served_gwh

                * 1_000_000

            )


            capex = _safe_float(

                thermal_source.get(
                    "capital_cost"
                ),

                0

            )


            om_cost = _safe_float(

                thermal_source.get(
                    "om_cost"
                ),

                0

            )


            lifetime = _safe_int(

                thermal_source.get(
                    "lifetime"
                ),

                25

            )


            crf = _compute_crf(

                0.03,
                lifetime

            )


            annual_capital_cost = (

                capacity_kw

                * capex

                * crf

            )


            annual_om_cost = (

                capacity_kw

                * om_cost

            )


            fuel_input_gwh = (

                useful_heat_generation_gwh

                / thermal_efficiency

                if thermal_efficiency > 0

                else 0

            )


            annual_fuel_cost = (

                fuel_input_gwh

                * 1_000_000

                * fuel_price

            )


            base_total_cost = (

                annual_capital_cost

                + annual_om_cost

                + annual_fuel_cost

            )


            inflation_rate = (

                _safe_float(

                    inflation.get(
                        str(year)
                    ),

                    2.5

                )

                / 100

            )


            years_from_base = max(

                year
                - start_year,

                0

            )


            inflation_multiplier = (

                (
                    1
                    + inflation_rate
                )

                ** years_from_base

            )


            annual_total_cost = (

                base_total_cost

                * inflation_multiplier

            )


            heat_cost = (

                annual_total_cost

                / served_heat_kwh

                if served_heat_kwh > 0

                else 0

            )


            row = {

                "region":
                    region_name,

                "year":
                    year,

                "fuel_type":
                    fuel_type,

                "thermal_load_gwh":
                    round(
                        thermal_load_gwh,
                        3
                    ),

                "thermal_generation_gwh":
                    round(
                        useful_heat_generation_gwh,
                        3
                    ),

                "thermal_served_gwh":
                    round(
                        thermal_served_gwh,
                        3
                    ),

                "storage_charged_gwh":
                    round(
                        storage_charged_gwh,
                        3
                    ),

                "storage_discharged_gwh":
                    round(
                        storage_discharged_gwh,
                        3
                    ),

                "storage_loss_gwh":
                    round(
                        storage_loss_gwh,
                        3
                    ),

                "stored_heat_gwh":
                    round(
                        stored_heat_gwh,
                        3
                    ),

                "thermal_surplus_gwh":
                    round(
                        thermal_surplus_gwh,
                        3
                    ),

                "unmet_thermal_gwh":
                    round(
                        unmet_thermal_gwh,
                        3
                    ),

                "annual_total_cost":
                    round(
                        annual_total_cost,
                        2
                    ),

                "heat_cost":
                    round(
                        heat_cost,
                        6
                    )

            }


            rows.append(
                row
            )


            energy_options[
                str(year)
            ][
                "Option 1"
            ][
                "Thermal"
            ] = round(

                thermal_served_gwh,
                3

            )


            energy_options[
                str(year)
            ][
                "Option 1"
            ][
                "COE"
            ] = round(

                heat_cost,
                6

            )


        return (

            rows,
            energy_options

        )


    # ============================================================
    # THERMAL MULTI LOCATION
    # ============================================================

    if run_mode == "multi":

        regions = (

            selected_regions

            or [
                active_region
            ]

        )


        all_rows = []

        results_by_region = {}


        for region in regions:

            (

                rows,
                options

            ) = simulate_region(
                region
            )


            all_rows.extend(
                rows
            )


            results_by_region[
                region
            ] = {

                "results":
                    rows,

                "energy_options":
                    options

            }


        return {

            "simulation_type":
                "thermal",

            "selected_regions":
                regions,

            "results":
                all_rows,

            "thermal_balance":
                all_rows,

            "results_by_region":
                results_by_region

        }


    rows, options = (
        simulate_region(
            active_region
        )
    )


    return {

        "simulation_type":
            "thermal",

        "selected_regions":
            [
                active_region
            ],

        "results":
            rows,

        "thermal_balance":
            rows,

        "energy_options":
            options

    }


# ============================================================
# MAIN SIMULATION ROUTE
#
# ONLY:
# - ELECTRICITY
# - HYDROGEN
# - THERMAL
# ============================================================

@app.route(
    "/api/run_simulation",
    methods=["POST"]
)
def run_simulation():

    try:

        data = (
            request.get_json()
            or {}
        )


        simulation_type = str(

            data.get(
                "simulation_type",
                "electric"
            )

        ).strip().lower()


        if simulation_type == (
            "hydrogen"
        ):

            output = (
                _run_hydrogen_simulation(
                    data
                )
            )


        elif simulation_type == (
            "thermal"
        ):

            output = (
                _run_thermal_simulation(
                    data
                )
            )


        elif simulation_type in [

            "electric",
            "electricity"

        ]:

            output = (
                _run_electricity_simulation(
                    data
                )
            )


        else:

            return jsonify({

                "error":
                    "Unsupported simulation type. Use electric, hydrogen, or thermal."

            }), 400


        return jsonify(
            output
        ), 200


    except Exception as error:

        traceback.print_exc()


        return jsonify({

            "error":
                str(error)

        }), 500


# ============================================================
# ECONOMIC ANALYSIS HELPERS
# ============================================================

def _economic_row_generation_mwh(
    row
):

    # Electricity
    if (

        row.get(
            "financial_energy_generated"
        )
        is not None

    ):

        return _safe_float(

            row.get(
                "financial_energy_generated"
            ),

            0

        )


    # Thermal
    if (

        row.get(
            "thermal_served_gwh"
        )
        is not None

    ):

        return (

            _safe_float(

                row.get(
                    "thermal_served_gwh"
                ),

                0

            )

            * 1000

        )


    # Hydrogen
    if (

        row.get(
            "fuel_cell_output_gwh"
        )
        is not None

    ):

        return (

            _safe_float(

                row.get(
                    "fuel_cell_output_gwh"
                ),

                0

            )

            * 1000

        )


    if (

        row.get(
            "energy_generated_gwh"
        )
        is not None

    ):

        return (

            _safe_float(

                row.get(
                    "energy_generated_gwh"
                ),

                0

            )

            * 1000

        )


    return _safe_float(

        row.get(
            "energy_generated"
        ),

        0

    )


def _economic_row_demand_mwh(
    row
):

    # Thermal
    if (

        row.get(
            "thermal_load_gwh"
        )
        is not None

    ):

        return (

            _safe_float(

                row.get(
                    "thermal_load_gwh"
                ),

                0

            )

            * 1000

        )


    # Hydrogen values use GWh.
    if (
        row.get(
            "source_type"
        )
        ==
        "Hydrogen"
    ):

        return (

            _safe_float(

                row.get(

                    "demand",

                    row.get(
                        "apple",
                        0
                    )

                ),

                0

            )

            * 1000

        )


    # Electricity demand is stored as MWh.
    return _safe_float(

        row.get(

            "demand",

            row.get(
                "apple",
                0
            )

        ),

        0

    )


def _compute_economic_dataset(
    rows,
    years,
    electricity_price,
    increase_rate,
    discount_rate,
    base_year,
    value_of_lost_load
):

    generation_by_year = defaultdict(
        float
    )


    demand_by_year = defaultdict(
        float
    )


    cost_by_year = defaultdict(
        float
    )


    seen_demand_keys = set()


    for row in rows:

        try:

            year = int(
                row.get(
                    "year"
                )
            )


        except (
            TypeError,
            ValueError
        ):

            continue


        generation_mwh = (
            _economic_row_generation_mwh(
                row
            )
        )


        generation_by_year[
            year
        ] += generation_mwh


        demand_mwh = (
            _economic_row_demand_mwh(
                row
            )
        )


        demand_key = (

            year,

            row.get(
                "option"
            ),

            row.get(
                "region"
            )

        )


        if (

            demand_mwh > 0

            and demand_key
            not in seen_demand_keys

        ):

            demand_by_year[
                year
            ] += demand_mwh


            seen_demand_keys.add(
                demand_key
            )


        annual_total_cost = _safe_float(

            row.get(
                "annual_total_cost"
            ),

            0

        )


        cost_by_year[
            year
        ] += annual_total_cost


    generation_data = []

    cash_flow_data = []


    total_generation = 0

    total_demand = 0

    total_served = 0

    total_surplus = 0

    total_unserved = 0


    present_value_cost = 0

    present_value_generation_kwh = 0

    present_value_revenue = 0


    for year in years:

        generation_mwh = (

            generation_by_year.get(
                year,
                0
            )

        )


        demand_mwh = (

            demand_by_year.get(
                year,
                0
            )

        )


        served_mwh = min(

            generation_mwh,
            demand_mwh

        )


        surplus_mwh = max(

            generation_mwh
            - demand_mwh,

            0

        )


        unserved_mwh = max(

            demand_mwh
            - generation_mwh,

            0

        )


        annual_cost = (

            cost_by_year.get(
                year,
                0
            )

        )


        outage_penalty = (

            unserved_mwh

            * 1000

            * value_of_lost_load

        )


        annual_cost_total = (

            annual_cost

            + outage_penalty

        )


        price_for_year = (

            electricity_price

            * (

                (
                    1
                    + increase_rate
                    / 100
                )

                ** (
                    year
                    - base_year
                )

            )

        )


        annual_revenue = (

            served_mwh

            * 1000

            * price_for_year

        )


        cash_flow = (

            annual_revenue

            - annual_cost_total

        )


        years_since_start = (

            year
            - base_year

        )


        discount_factor = (

            1
            /
            (
                (
                    1
                    + discount_rate
                )

                ** years_since_start
            )

            if years_since_start >= 0

            else 1

        )


        present_value_cost += (

            annual_cost_total

            * discount_factor

        )


        present_value_generation_kwh += (

            served_mwh

            * 1000

            * discount_factor

        )


        present_value_revenue += (

            annual_revenue

            * discount_factor

        )


        total_generation += (
            generation_mwh
        )


        total_demand += (
            demand_mwh
        )


        total_served += (
            served_mwh
        )


        total_surplus += (
            surplus_mwh
        )


        total_unserved += (
            unserved_mwh
        )


        generation_data.append({

            "year":
                year,

            "demand":
                round(
                    demand_mwh,
                    3
                ),

            "served_energy":
                round(
                    served_mwh,
                    3
                ),

            "generation":
                round(
                    generation_mwh,
                    3
                ),

            "surplus":
                round(
                    surplus_mwh,
                    3
                ),

            "unserved_energy":
                round(
                    unserved_mwh,
                    3
                ),

            "annual_cost":
                round(
                    annual_cost,
                    2
                ),

            "outage_penalty":
                round(
                    outage_penalty,
                    2
                ),

            "annual_cost_total":
                round(
                    annual_cost_total,
                    2
                ),

            "annual_revenue":
                round(
                    annual_revenue,
                    2
                )

        })


        cash_flow_data.append({

            "year":
                year,

            "cash_flow":
                round(
                    cash_flow,
                    2
                )

        })


    total_annual_cost = sum(

        cost_by_year.get(
            year,
            0
        )

        for year
        in years

    )


    total_outage_penalty = (

        total_unserved

        * 1000

        * value_of_lost_load

    )


    total_annual_revenue = sum(

        row.get(
            "annual_revenue",
            0
        )

        for row
        in generation_data

    )


    generation_data.append({

        "year":
            "Total",

        "demand":
            round(
                total_demand,
                3
            ),

        "served_energy":
            round(
                total_served,
                3
            ),

        "generation":
            round(
                total_generation,
                3
            ),

        "surplus":
            round(
                total_surplus,
                3
            ),

        "unserved_energy":
            round(
                total_unserved,
                3
            ),

        "annual_cost":
            round(
                total_annual_cost,
                2
            ),

        "outage_penalty":
            round(
                total_outage_penalty,
                2
            ),

        "annual_cost_total":
            round(

                total_annual_cost
                + total_outage_penalty,

                2

            ),

        "annual_revenue":
            round(
                total_annual_revenue,
                2
            )

    })


    net_present_cost = (

        present_value_cost

        / 1_000_000

    )


    lcoe = (

        present_value_cost

        / present_value_generation_kwh

        if present_value_generation_kwh > 0

        else 0

    )


    net_present_value = (

        present_value_revenue

        - present_value_cost

    ) / 1_000_000


    return {

        "generation_data":
            generation_data,

        "cash_flow":
            cash_flow_data,

        "summary": {

            "electricity_price":
                electricity_price,

            "increasing_rate":
                increase_rate,

            "discount_rate":
                discount_rate,

            "value_of_lost_load":
                value_of_lost_load,

            "net_present_cost":
                round(
                    net_present_cost,
                    3
                ),

            "lcoe":
                round(
                    lcoe,
                    5
                ),

            "net_present_value":
                round(
                    net_present_value,
                    3
                )

        }

    }


# ============================================================
# ECONOMIC ANALYSIS ROUTE
# ============================================================

@app.route(
    "/api/economic_analysis",
    methods=["POST"]
)
def economic_analysis():

    try:

        data = (
            request.get_json()
            or {}
        )


        results = (

            data.get(
                "results"
            )

            or []

        )


        years_filter = data.get(
            "years"
        )


        mode = str(

            data.get(
                "mode",
                "both"
            )

        )


        selected_region = (
            data.get(
                "selected_region"
            )
        )


        electricity_price = _safe_float(

            data.get(
                "electricity_price"
            ),

            0.10

        )


        increase_rate = _safe_float(

            data.get(
                "increase_rate"
            ),

            5

        )


        discount_rate = _safe_float(

            data.get(
                "discount_rate"
            ),

            0.03

        )


        base_year = _safe_int(

            data.get(
                "base_year"
            ),

            2025

        )


        value_of_lost_load = _safe_float(

            data.get(
                "value_of_lost_load"
            ),

            2

        )


        active_results = (
            results
        )


        if (

            mode == "region"

            and selected_region

        ):

            active_results = [

                row

                for row
                in results

                if (
                    row.get(
                        "region"
                    )
                    ==
                    selected_region
                )

            ]


        if years_filter:

            years = []


            for value in (
                years_filter
            ):

                try:

                    years.append(
                        int(
                            value
                        )
                    )


                except (
                    TypeError,
                    ValueError
                ):

                    continue


        else:

            years = sorted({

                int(
                    row.get(
                        "year"
                    )
                )

                for row
                in active_results

                if str(
                    row.get(
                        "year",
                        ""
                    )
                ).isdigit()

            })


        aggregated = (
            _compute_economic_dataset(

                active_results,
                years,
                electricity_price,
                increase_rate,
                discount_rate,
                base_year,
                value_of_lost_load

            )
        )


        per_region = {}


        all_regions = sorted({

            row.get(
                "region"
            )

            for row
            in results

            if row.get(
                "region"
            )

        })


        for region in all_regions:

            region_rows = [

                row

                for row
                in results

                if (
                    row.get(
                        "region"
                    )
                    ==
                    region
                )

            ]


            per_region[
                region
            ] = (

                _compute_economic_dataset(

                    region_rows,
                    years,
                    electricity_price,
                    increase_rate,
                    discount_rate,
                    base_year,
                    value_of_lost_load

                )

            )


        return jsonify({

            "mode":
                mode,

            "selected_region":
                selected_region,

            "aggregated":
                aggregated,

            "per_region":
                per_region,

            # Also expose these directly because
            # the simplified frontend checks them.

            "generation_data":
                aggregated[
                    "generation_data"
                ],

            "cash_flow":
                aggregated[
                    "cash_flow"
                ],

            "summary":
                aggregated[
                    "summary"
                ]

        }), 200


    except Exception as error:

        traceback.print_exc()


        return jsonify({

            "error":
                str(error)

        }), 500


# ============================================================
# DISABLED ROUTES
# ============================================================

"""
These routes are NOT active:

@app.route('/api/run_resiliency')
@app.route('/api/run_multi_energy_resiliency')
@app.route('/api/hurricane_resilience/analyze')
@app.route('/api/framework/library')
@app.route('/api/smr_human_performance/evaluate')
@app.route('/api/admin/users')

They can be restored later if required.
"""


# ============================================================
# CREATE MISSING TABLES
#
# IMPORTANT:
# This is outside __main__ so Render/Gunicorn
# also creates location_sizing_limits_v2.
# ============================================================

with app.app_context():

    db.create_all()


# ============================================================
# LOCAL START
# ============================================================

if __name__ == "__main__":

    app.run(

        host=
            "0.0.0.0",

        port=
            int(
                os.environ.get(
                    "PORT",
                    5000
                )
            ),

        debug=(
            os.getenv(
                "FLASK_DEBUG",
                "0"
            )
            ==
            "1"
        )

    )