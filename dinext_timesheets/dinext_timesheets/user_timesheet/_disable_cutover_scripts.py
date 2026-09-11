"""Disable legacy UT Client/Server Scripts after app cutover.

ISS-2026-00926 try3. List: try3/timesheet/cutover-disable-scripts.md
Does not touch JE API SS. Limits calculator is PWA.
"""

from __future__ import annotations

import frappe

CLIENT_SCRIPTS = (
	"User_Timesheet_Position_to_User_Timesheet_form_integration_V10",
	"User_Timesheet_Position_to_User_Timesheet_form_integration_V10_OLD",
	"UT_Accept_WF",
	"Copy Previous UT",
	"Check Limits_V2",
	"Show Plan-Actual Data_V2",
	"User_Timesheet_Status_Color",
	"UT List Reprocess JE",
	"Custom_ListView_6",
	"UTP_History_Data",
	"User Timesheet Position Function_V3",
	"UTP_ListView_Style_2",
	"UTP_Route",
	"UT_List_Period_Filter_V2",
)

SERVER_SCRIPTS = (
	"UT Get Task List",
	"Copy_Positions_From_Previous_Timesheet",
	"Copy_Positions_From_Project_Workload_Assignment",
	"Set Timesheet Status",
	"UT_Hours_Calculate_V4",
	"UT_Set_User_Group",
	"Create Journal Entries UT After Save",
	"All_Hours_Calculate",
	"Utilization_Hours_V2",
	"UTP_Set_User_Group",
	"User_Equals_Owner",
	"Timesheet_Position_Period",
	"UTP Check WT Before Save V2",
	"UTP Proccess WT After Save",
	"UTP_Deleted_WTs_Deleted",
	"UTP_UT_Status_V3",
	"UTP_UT_Status_V3_OLD",
	"Task Limit Exceeded_V4",
	"Calculate Timesheet Limits_V4",
	"UTP_comm_2_UT_transfer",
	"TSCrW2",
)


def run():
	result = {"client_script": [], "server_script": []}

	for name in CLIENT_SCRIPTS:
		if not frappe.db.exists("Client Script", name):
			result["client_script"].append(f"missing:{name}")
			continue
		frappe.db.set_value("Client Script", name, "enabled", 0)
		result["client_script"].append(f"disabled:{name}")

	for name in SERVER_SCRIPTS:
		if not frappe.db.exists("Server Script", name):
			result["server_script"].append(f"missing:{name}")
			continue
		frappe.db.set_value("Server Script", name, "disabled", 1)
		result["server_script"].append(f"disabled:{name}")

	frappe.clear_cache()
	frappe.db.commit()
	return result
