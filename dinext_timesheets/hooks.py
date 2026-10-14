app_name = "dinext_timesheets"
app_title = "Dinext Timesheets"
app_publisher = "Dinext"
app_description = "Dinext Timesheets"
app_email = "info@dinext.ru"
app_license = "GNU General Public License (v3)"

# closeout-decouple live probe 2 (2026-09-19)

# Apps
# ------------------

fixtures = [
    "Type Of Leave",    
    "Workflow State",
    "Workflow Action Master",    
    {
        "doctype": "Calendar View",
        "filters": [
            ["name", "in", ["AFL"]]
        ]
    },
    {
        "doctype": "Custom Field",
        "filters": [
            ["module", "in", ["Dinext Timesheets"]]
        ]
    },
    {
        "doctype": "Property Setter",
        "filters": [
            ["module", "in", ["Dinext Timesheets"]]
        ]
    },
    {
        "doctype": "Client Script",
        "filters": [
            ["module", "in", ["Dinext Timesheets"]],
        ]
    },
    {
        "doctype": "Server Script",
        "filters": [
            ["module", "in", ["Dinext Timesheets"]],
        ]
    },
    {
        "doctype": "Web Page",
        "filters": [
            ["module", "in", ["Dinext Timesheets"]],       
        ]
    },    
    {
        "doctype": "Timesheet Template",
        "filters": [
            ["name", "in", "Внутренняя команда РФ"]
        ]
    },
    {
        "doctype": "Working Hours On Date",
        "filters": [
            ["name", "in", ["Сокращенные рабочие дни РФ"]]
        ]
    },
    {
        "doctype": "Workflow",
        "filters": [
            ["document_type", "in", ["Application For Leave", "User Timesheet Position"]],
            ["is_active", "=", 1]            
        ]
    },
    {
        "doctype": "Role",
        "filters": [
            ["name", "in", [
                "Dinext_UTP_Appoval",
                "Dinext_UT_Full_Access",
                "Dinext_Projects_Director",
                "Dinext_Projects_Admin",
            ]],
            ["disabled", "=", 0]
        ]
    },
    {
        "doctype": "Custom DocPerm",
        "filters": [
            ["parent", "in", [
                "Timesheet Template",
                "User Timesheet",
                "User Timesheet Position",
                "User Timesheet Position Details",
                "Application For Leave",
                "Type Of Leave",
                "Working Hours Table",
                "Doctype For Timesheet",
                "User Projects",
                "Worker",
                "Working Hours On Date",
                "Workflow Task",
            ]]
        ]
    },    
    {
        "doctype": "DocType Permission",
        "filters": [
            ["ref_doctype", "in", 
                [
                    "Timesheet Template",
                    "User Timesheet",
                    "User Timesheet Position",
                    "Application For Leave",
                    "Worker",
                ]
            ],
            ["docstatus", "!=", 2]            
        ]
    }
]

required_apps = ["dinext_common", "dinext_projects", "dinext_projects_pl", "doctype_permission"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "dinext_timesheets",
# 		"logo": "/assets/dinext_timesheets/logo.png",
# 		"title": "Dinext Timesheets",
# 		"route": "/dinext_timesheets",
# 		"has_permission": "dinext_timesheets.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/dinext_timesheets/css/dinext_timesheets.css"
# app_include_js = "/assets/dinext_timesheets/js/dinext_timesheets.js"

# include js, css files in header of web template
# web_include_css = "/assets/dinext_timesheets/css/dinext_timesheets.css"
# web_include_js = "/assets/dinext_timesheets/js/dinext_timesheets.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "dinext_timesheets/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# User Timesheet UI → public/js/user_timesheet (ISS-2026-00926 try3)
doctype_js = {
	"User Timesheet": [
		"public/js/user_timesheet/entry.js",
	],
	"User Timesheet Position": [
		"public/js/user_timesheet_position_form.js",
		"public/js/user_timesheet_position/form/route.js",
	],
}
doctype_list_js = {
	"User Timesheet": [
		# reprocess helpers before status_color onload
		"public/js/user_timesheet/list/reprocess_je.js",
		"public/js/user_timesheet/list/status_color.js",
	],
	"User Timesheet Position": [
		"public/js/user_timesheet_position_list.js",
		"public/js/user_timesheet_position/list/style.js",
		"public/js/user_timesheet_position/list/period_filter.js",
		"public/js/user_timesheet_position/list/functions.js",
		"public/js/user_timesheet_position/list/history.js",
		"public/js/user_timesheet_position/list/custom_listview.js",
	],
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "dinext_timesheets/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "dinext_timesheets.utils.jinja_methods",
# 	"filters": "dinext_timesheets.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "dinext_timesheets.install.before_install"
after_install = "dinext_timesheets.install.after_install"
after_migrate = "dinext_timesheets.install.after_migrate"
extend_bootinfo = ["dinext_timesheets.boot.extend_bootinfo"]

# Uninstallation
# ------------

# before_uninstall = "dinext_timesheets.uninstall.before_uninstall"
# after_uninstall = "dinext_timesheets.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "dinext_timesheets.utils.before_app_install"
# after_app_install = "dinext_timesheets.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "dinext_timesheets.utils.before_app_uninstall"
# after_app_uninstall = "dinext_timesheets.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "dinext_timesheets.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events
# User Timesheet domain events (ISS-2026-00926 try3 phase 2 block A)
# Canon bodies: demodev Server Scripts — disable matching SS on site after cutover.

doc_events = {
	"User Timesheet": {
		"before_save": "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet.before_save",
		# Server Script "After Save" ≡ Document.on_update (JE create/cancel)
		"on_update": "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet.on_update",
	},
	"User Timesheet Position": {
		"before_insert": "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet_position.before_insert",
		"before_save": "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet_position.before_save",
		# Server Script "After Save" ≡ Document.on_update
		# Layer 3 ISS-2026-03288: UTP→UT rollup + Task act_* (SS UTP_UT_Status_V3 disabled local)
		"on_update": [
			"dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet_position.on_update",
			"dinext_timesheets.workflow_approval.on_utp_update",
		],
		"on_trash": "dinext_timesheets.dinext_timesheets.user_timesheet.events.user_timesheet_position.on_trash",
	},
	"Comment": {
		# Server Script "After Insert" ≡ Document.after_insert
		"after_insert": [
			"dinext_timesheets.dinext_timesheets.user_timesheet.events.comment.transfer_utp_comment_to_ut",
			"dinext_timesheets.workflow_approval.mirror_utp_comment",
		],
	},
}

workflow_approval_lock_dependencies = [
	"dinext_timesheets.workflow_approval.lock_dependencies",
]
workflow_approval_pending_approvers = [
	"dinext_timesheets.workflow_approval.pending_approvers",
]
workflow_approval_vote_completed = [
	"dinext_timesheets.workflow_approval.on_vote_completed",
]
workflow_approval_digest_item = [
	"dinext_timesheets.workflow_approval.digest_item",
]

# Scheduled Tasks
# ---------------
# TSCrW2 weekly UT create (ISS-2026-00926 phase 2 F). Demodev cron: Mon 08:30.

scheduler_events = {
	"cron": {
		"30 8 * * 1": [
			"dinext_timesheets.dinext_timesheets.user_timesheet.scheduler.create_weekly_timesheets",
		],
	},
}

# Testing
# -------

# before_tests = "dinext_timesheets.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "dinext_timesheets.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "dinext_timesheets.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["dinext_timesheets.utils.before_request"]
# after_request = ["dinext_timesheets.utils.after_request"]

# Job Events
# ----------
# before_job = ["dinext_timesheets.utils.before_job"]
# after_job = ["dinext_timesheets.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"dinext_timesheets.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

