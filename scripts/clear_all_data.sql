-- ============================================================
-- CLEAR ALL APPLICATION DATA
-- Keeps tables and Django migration records intact.
-- Run in SQL Server Management Studio / Azure Data Studio.
-- ============================================================

PRINT 'Step 1: Disabling all foreign key constraints...'
EXEC sp_MSforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL'

-- ============================================================
-- RECRUITMENT AGENT


-- ============================================================
PRINT 'Clearing recruitment_agent tables...'
DELETE FROM [ppp_recruitment_agent_recruitmentqachatmessage]
DELETE FROM [ppp_recruitment_agent_recruitmentqachat]
DELETE FROM [ppp_recruitment_agent_savedgraphprompt]
DELETE FROM [ppp_recruitment_agent_interview]
DELETE FROM [ppp_recruitment_agent_cvrecord]
DELETE FROM [ppp_recruitment_job_applications]
DELETE FROM [ppp_recruitment_agent_careerapplication]
DELETE FROM [ppp_recruitment_agent_jobdescription]
DELETE FROM [ppp_recruitment_agent_recruiterinterviewsettings]
DELETE FROM [ppp_recruitment_agent_recruiterqualificationsettings]
DELETE FROM [ppp_recruitment_agent_recruiteremailsettings]

-- ============================================================
-- AI SDR AGENT
-- ============================================================
PRINT 'Clearing ai_sdr_agent tables...'
DELETE FROM [sdr_outreach_log]
DELETE FROM [sdr_campaign_enrollment]
DELETE FROM [sdr_campaign_step]
DELETE FROM [sdr_meeting]
DELETE FROM [sdr_campaign]
DELETE FROM [sdr_lead]
DELETE FROM [sdr_lead_research_job]
DELETE FROM [sdr_icp_profile]
DELETE FROM [sdr_agent_settings]

-- ============================================================
-- MARKETING AGENT
-- ============================================================
PRINT 'Clearing marketing_agent tables...'
DELETE FROM [ppp_marketingagent_emailsendhistory]
DELETE FROM [ppp_marketingagent_emailsequencestep]
DELETE FROM [ppp_marketingagent_emailsequence]
DELETE FROM [ppp_marketingagent_emailtemplate]
DELETE FROM [ppp_marketingagent_reply]
DELETE FROM [ppp_marketingagent_campaigncontact]
DELETE FROM [ppp_marketingagent_campaign_leads]
DELETE FROM [ppp_marketingagent_campaignperformance]
DELETE FROM [ppp_marketingagent_campaign]
DELETE FROM [ppp_marketingagent_lead]
DELETE FROM [ppp_marketingagent_marketresearchchatmessage]
DELETE FROM [ppp_marketingagent_marketresearchchat]
DELETE FROM [ppp_marketingagent_marketingqachatmessage]
DELETE FROM [ppp_marketingagent_marketingqachat]
DELETE FROM [ppp_marketingagent_marketresearch]
DELETE FROM [ppp_marketingagent_marketingnotification]
DELETE FROM [ppp_marketingagent_notificationrule]
DELETE FROM [ppp_marketingagent_marketingdocument]
DELETE FROM [ppp_marketingagent_emailaccount]
DELETE FROM [ppp_marketing_agent_savedgraphprompt]

-- ============================================================
-- REPLY DRAFT AGENT
-- ============================================================
PRINT 'Clearing reply_draft_agent tables...'
DELETE FROM [ppp_replydraftagent_replydraftattachment]
DELETE FROM [ppp_replydraftagent_replydraft]
DELETE FROM [ppp_replydraftagent_inboxattachment]
DELETE FROM [ppp_replydraftagent_inboxemail]

-- ============================================================
-- FRONTLINE AGENT
-- ============================================================
PRINT 'Clearing frontline_agent tables...'
DELETE FROM [frontline_agent_ticketsatisfaction]
DELETE FROM [frontline_agent_ticketlink]
DELETE FROM [frontline_agent_contactnote]
DELETE FROM [frontline_agent_ticketnote]
DELETE FROM [frontline_agent_ticketmessage]
DELETE FROM [frontline_agent_ticketattachment]
DELETE FROM [frontline_agent_ticket]
DELETE FROM [frontline_agent_frontlinedeadletter]
DELETE FROM [frontline_agent_ticketmacro]
DELETE FROM [frontline_agent_contact]
DELETE FROM [frontline_agent_frontlineauditlog]
DELETE FROM [frontline_agent_llmusage]
DELETE FROM [frontline_agent_documentchunk]
DELETE FROM [frontline_agent_kbfeedback]
DELETE FROM [frontline_agent_knowledgebase]
DELETE FROM [frontline_agent_frontlineqachatmessage]
DELETE FROM [frontline_agent_frontlineqachat]
DELETE FROM [frontline_agent_frontlineworkflowexecution]
DELETE FROM [frontline_agent_frontlineworkflowversion]
DELETE FROM [frontline_agent_frontlineworkflow]
DELETE FROM [frontline_agent_schedulednotification]
DELETE FROM [frontline_agent_notificationtemplate]
DELETE FROM [frontline_agent_frontlinenotificationpreferences]
DELETE FROM [frontline_agent_notification]
DELETE FROM [frontline_agent_frontlineanalytics]
DELETE FROM [frontline_agent_frontlinemeeting]
DELETE FROM [frontline_agent_document]
DELETE FROM [frontline_agent_savedgraphprompt]

-- ============================================================
-- HR AGENT
-- ============================================================
PRINT 'Clearing hr_agent tables...'
DELETE FROM [hr_agent_hrdocumentaccesslog]
DELETE FROM [hr_agent_hrauditlog]
DELETE FROM [hr_agent_hrknowledgechatmessage]
DELETE FROM [hr_agent_hrknowledgechat]
DELETE FROM [hr_agent_hrmeetingschedulerchatmessage]
DELETE FROM [hr_agent_hrmeetingschedulerchat]
DELETE FROM [hr_agent_hrschedulednotification]
DELETE FROM [hr_agent_hrnotificationtemplate]
DELETE FROM [hr_agent_hrmeeting]
DELETE FROM [hr_agent_hrworkflowexecution]
DELETE FROM [hr_agent_hrworkflow]
DELETE FROM [hr_agent_hrdocumentchunk]
DELETE FROM [hr_agent_hrdocument]
DELETE FROM [hr_agent_performancegoal]
DELETE FROM [hr_agent_performancereview]
DELETE FROM [hr_agent_performancereviewcycle]
DELETE FROM [hr_agent_compensation]
DELETE FROM [hr_agent_leaverequest]
DELETE FROM [hr_agent_leaveaccrualpolicy]
DELETE FROM [hr_agent_leavebalance]
DELETE FROM [hr_agent_holiday]
DELETE FROM [hr_agent_employee]
DELETE FROM [hr_agent_department]

-- ============================================================
-- OPERATIONS AGENT
-- ============================================================
PRINT 'Clearing operations_agent tables...'
DELETE FROM [operations_agent_operationsnotification]
DELETE FROM [operations_agent_operationschatmessage]
DELETE FROM [operations_agent_operationschat]
DELETE FROM [operations_agent_operationsgenerateddocument]
DELETE FROM [operations_agent_operationsanalyticssnapshot]
DELETE FROM [operations_agent_operationsdocumentchunk]
DELETE FROM [operations_agent_operationsdocumentsummary]
DELETE FROM [operations_agent_operationsdocument]

-- ============================================================
-- PROJECT MANAGER AGENT
-- ============================================================
PRINT 'Clearing project_manager_agent tables...'
DELETE FROM [project_manager_agent_meetingresponse]
DELETE FROM [project_manager_agent_meetingparticipant]
DELETE FROM [project_manager_agent_scheduledmeeting]
DELETE FROM [project_manager_agent_pmauditlog]
DELETE FROM [project_manager_agent_pmnotification]
DELETE FROM [project_manager_agent_pmnotificationtemplate]
DELETE FROM [project_manager_agent_pmnotificationchannel]
DELETE FROM [project_manager_agent_pmmeetingschedulerchatmessage]
DELETE FROM [project_manager_agent_pmmeetingschedulerchat]
DELETE FROM [project_manager_agent_pmprojectpilotchatmessage]
DELETE FROM [project_manager_agent_pmprojectpilotchat]
DELETE FROM [project_manager_agent_pmknowledgeqachatmessage]
DELETE FROM [project_manager_agent_pmknowledgeqachat]

-- ============================================================
-- CRM SYNC AGENT (skipped — tables not yet in DB)
-- ============================================================

-- ============================================================
-- CORE APP — Tasks, Projects, etc.
-- ============================================================
PRINT 'Clearing core app tables...'
DELETE FROM [core_commentattachment]
DELETE FROM [core_taskcomment]
DELETE FROM [core_taskactivitylog]
DELETE FROM [core_taskattachment]
DELETE FROM [core_timeentry]
DELETE FROM [core_timersession]
DELETE FROM [core_projecthealthscore]
DELETE FROM [core_projectrisk]
DELETE FROM [core_projectissue]
DELETE FROM [core_subtask]
DELETE FROM [core_taskrecurrence]
DELETE FROM [core_tasktag]
DELETE FROM [core_task]
DELETE FROM [core_projectmilestone]
DELETE FROM [core_projectdocument]
DELETE FROM [core_projectapplication]
DELETE FROM [core_project]
DELETE FROM [core_teammember]
DELETE FROM [core_meeting]
DELETE FROM [core_actionitem]
DELETE FROM [core_workflowexecution]
DELETE FROM [core_workflowstep]
DELETE FROM [core_workflow]
DELETE FROM [core_dashboardview]
DELETE FROM [core_analytics]
DELETE FROM [core_analyticsevent]
DELETE FROM [core_pageview]
DELETE FROM [core_notification]
DELETE FROM [core_notificationpreference]
DELETE FROM [core_emaillog]
DELETE FROM [core_emailreminder]
DELETE FROM [core_emailtemplate]
DELETE FROM [core_aipredictorsubmission]
DELETE FROM [core_quizresponse]
DELETE FROM [core_talentrequest]
DELETE FROM [core_chatbotmessage]
DELETE FROM [core_chatbotconversation]
DELETE FROM [core_consultation]
DELETE FROM [core_complaint]
DELETE FROM [core_contactmessage]
DELETE FROM [core_review]
DELETE FROM [core_faq]
DELETE FROM [core_blogposttag]
DELETE FROM [core_blogpost]
DELETE FROM [core_blogtag]
DELETE FROM [core_referral]
DELETE FROM [core_referralcode]
DELETE FROM [core_credittransaction]
DELETE FROM [core_credit]
DELETE FROM [core_payment]
DELETE FROM [core_paymentmethod]
DELETE FROM [core_invoice]
DELETE FROM [core_subscription]
DELETE FROM [core_pricingplan]
DELETE FROM [core_whitelabelproduct]
DELETE FROM [core_industrychallenge]
DELETE FROM [core_industry]
DELETE FROM [core_useractivitylog]
DELETE FROM [core_userverification]
DELETE FROM [core_usersession]
DELETE FROM [core_agentproviderusage]
DELETE FROM [core_agenttokenquota]
DELETE FROM [core_companyapikey]
DELETE FROM [core_keyrequest]
DELETE FROM [core_adminpricingconfig]
DELETE FROM [core_platformapikey]
DELETE FROM [core_companymodulepurchase]
DELETE FROM [core_companyusertoken]
DELETE FROM [core_companyregistrationtoken]
DELETE FROM [core_companyuser]
DELETE FROM [core_company]
DELETE FROM [core_userprofile]

-- ============================================================
-- DJANGO AUTH TABLES (users, sessions, admin log)
-- ============================================================
PRINT 'Clearing Django auth / session tables...'
DELETE FROM [django_admin_log]
DELETE FROM [django_session]
DELETE FROM [auth_user_user_permissions]
DELETE FROM [auth_user_groups]
DELETE FROM [auth_user]
DELETE FROM [auth_group_permissions]
DELETE FROM [auth_group]

-- ============================================================
-- NOTE: The following are intentionally NOT cleared:
--   django_migrations    — keeps DB schema in sync
--   django_content_type  — auto-rebuilt by Django on next run
--   auth_permission      — auto-rebuilt by Django on next run
-- ============================================================

PRINT 'Step 2: Re-enabling all foreign key constraints...'
EXEC sp_MSforeachtable 'ALTER TABLE ? CHECK CONSTRAINT ALL'

-- ============================================================
-- Reset identity columns back to 0 (IDs restart from 1)
-- ============================================================
PRINT 'Resetting identity columns...'
EXEC sp_MSforeachtable '
    IF EXISTS (
        SELECT 1 FROM sys.identity_columns
        WHERE OBJECT_NAME(object_id) = PARSENAME(''?'', 1)
    )
    BEGIN
        DBCC CHECKIDENT (''?'', RESEED, 0)
    END
'

PRINT '✓ All data cleared. All IDs will restart from 1.'
