// Generated from contracts/openapi.json. Do not edit.
export interface paths {
    "/api/v1/agent-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Agent Run */
        get: operations["get_agent_run_api_v1_agent_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Agent Run */
        post: operations["cancel_agent_run_api_v1_agent_runs__run_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}/output": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Agent Run Output */
        get: operations["get_agent_run_output_api_v1_agent_runs__run_id__output_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Stream Agent Run */
        post: operations["stream_agent_run_api_v1_agent_runs__run_id__stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{approval_id}/decision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Gate Approval */
        post: operations["decide_gate_approval_api_v1_approvals__approval_id__decision_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/capability-requests/{request_id}/decision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Capability */
        post: operations["decide_capability_api_v1_capability_requests__request_id__decision_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/events/replay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Replay Events */
        get: operations["replay_events_api_v1_events_replay_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/events/tickets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Issue Event Ticket */
        post: operations["issue_event_ticket_api_v1_events_tickets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/model-profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Profiles */
        get: operations["list_profiles_api_v1_model_profiles_get"];
        put?: never;
        /** Create Profile */
        post: operations["create_profile_api_v1_model_profiles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/model-profiles/{profile_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Profile */
        get: operations["get_profile_api_v1_model_profiles__profile_id__get"];
        /** Update Profile */
        put: operations["update_profile_api_v1_model_profiles__profile_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_api_v1_projects_get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_api_v1_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_api_v1_projects__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/checkpoints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Checkpoints */
        get: operations["list_checkpoints_api_v1_projects__project_id__checkpoints_get"];
        put?: never;
        /** Create Checkpoint */
        post: operations["create_checkpoint_api_v1_projects__project_id__checkpoints_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Checkpoint */
        post: operations["restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/checkpoints/{checkpoint_id}/restore-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Plan Restore */
        post: operations["plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Close Project */
        post: operations["close_project_api_v1_projects__project_id__close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/conflicts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conflicts */
        get: operations["list_conflicts_api_v1_projects__project_id__conflicts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/conflicts/{conflict_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve Conflict */
        post: operations["resolve_conflict_api_v1_projects__project_id__conflicts__conflict_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/external-changes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List External Changes */
        get: operations["list_external_changes_api_v1_projects__project_id__external_changes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/external-changes/scan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Scan External Changes */
        post: operations["scan_external_changes_api_v1_projects__project_id__external_changes_scan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/open": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Open Project */
        post: operations["open_project_api_v1_projects__project_id__open_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/preflight": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Preflight */
        get: operations["get_preflight_api_v1_projects__project_id__preflight_get"];
        put?: never;
        /** Run Preflight */
        post: operations["run_preflight_api_v1_projects__project_id__preflight_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/workflows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Workflows */
        get: operations["list_workflows_api_v1_projects__project_id__workflows_get"];
        put?: never;
        /** Create Workflow */
        post: operations["create_workflow_api_v1_projects__project_id__workflows_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_api_v1_readiness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/recovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Recoveries */
        get: operations["list_recoveries_api_v1_recovery_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/recovery/{recovery_id}/{action}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve Recovery */
        post: operations["resolve_recovery_api_v1_recovery__recovery_id___action__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rooms/{room_id}/agent-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Agent Runs */
        get: operations["list_agent_runs_api_v1_rooms__room_id__agent_runs_get"];
        put?: never;
        /** Create Agent Run */
        post: operations["create_agent_run_api_v1_rooms__room_id__agent_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rooms/{room_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Messages */
        get: operations["list_messages_api_v1_rooms__room_id__messages_get"];
        put?: never;
        /** Append Message */
        post: operations["append_message_api_v1_rooms__room_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rooms/{room_id}/model-assignment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Room Assignment */
        get: operations["get_room_assignment_api_v1_rooms__room_id__model_assignment_get"];
        /** Assign Room Models */
        put: operations["assign_room_models_api_v1_rooms__room_id__model_assignment_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rooms/{room_id}/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enqueue Task */
        post: operations["enqueue_task_api_v1_rooms__room_id__tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/stage-runs/{stage_run_id}/artifact-versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Artifact Version */
        post: operations["create_artifact_version_api_v1_stage_runs__stage_run_id__artifact_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/stage-runs/{stage_run_id}/quality-gates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Evaluate Quality Gate */
        post: operations["evaluate_quality_gate_api_v1_stage_runs__stage_run_id__quality_gates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/control": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Desktop Control */
        get: operations["desktop_control_api_v1_system_control_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/info": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** System Info */
        get: operations["system_info_api_v1_system_info_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/system/shutdown": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Shutdown */
        post: operations["request_shutdown_api_v1_system_shutdown_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Task */
        post: operations["cancel_task_api_v1_tasks__task_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/capability-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Capability */
        post: operations["request_capability_api_v1_tasks__task_id__capability_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete Task */
        post: operations["complete_task_api_v1_tasks__task_id__complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Task */
        post: operations["start_task_api_v1_tasks__task_id__start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/tool-calls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Execute Tool */
        post: operations["execute_tool_api_v1_tasks__task_id__tool_calls_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tool-calls/{call_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Tool Call */
        post: operations["cancel_tool_call_api_v1_tool_calls__call_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tools/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tool Catalog */
        get: operations["list_tool_catalog_api_v1_tools_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workflow */
        get: operations["get_workflow_api_v1_workflows__workflow_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/approvals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Approvals */
        get: operations["list_approvals_api_v1_workflows__workflow_id__approvals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Artifacts */
        get: operations["list_artifacts_api_v1_workflows__workflow_id__artifacts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/capability-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Capability Requests */
        get: operations["list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/change-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Change Requests */
        get: operations["list_change_requests_api_v1_workflows__workflow_id__change_requests_get"];
        put?: never;
        /** Create Change Request */
        post: operations["create_change_request_api_v1_workflows__workflow_id__change_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/handoffs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Handoffs */
        get: operations["list_handoffs_api_v1_workflows__workflow_id__handoffs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/mode": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Set Workflow Mode */
        post: operations["set_workflow_mode_api_v1_workflows__workflow_id__mode_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/orchestration/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Orchestrate Workflow Stage */
        post: operations["orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/quality-gates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Quality Gates */
        get: operations["list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/stage-runs/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Stage History */
        get: operations["list_stage_history_api_v1_workflows__workflow_id__stage_runs_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/stages/{stage}/reopen": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reopen Stage */
        post: operations["reopen_stage_api_v1_workflows__workflow_id__stages__stage__reopen_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/stages/{stage}/transition": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Transition Stage */
        post: operations["transition_stage_api_v1_workflows__workflow_id__stages__stage__transition_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Workflow */
        post: operations["start_workflow_api_v1_workflows__workflow_id__start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tasks */
        get: operations["list_tasks_api_v1_workflows__workflow_id__tasks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/tool-calls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tool Calls */
        get: operations["list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{workflow_id}/{action}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Control Workflow */
        post: operations["control_workflow_api_v1_workflows__workflow_id___action__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ActorRef */
        ActorRef: {
            /** Id */
            id?: string | null;
            type: components["schemas"]["ActorType"];
        };
        /**
         * ActorType
         * @enum {string}
         */
        ActorType: "system" | "user" | "worker" | "model" | "tool";
        /** AgentRun */
        AgentRun: {
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code?: string | null;
            /** Final Output Bytes */
            final_output_bytes?: number | null;
            /** Final Output Hash */
            final_output_hash?: string | null;
            /** Final Output Ref */
            final_output_ref?: string | null;
            /** Formal */
            formal: boolean;
            /** Id */
            id: string;
            /** Request Key */
            request_key: string;
            /** Room Id */
            room_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["AgentRunStatus"];
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** AgentRunCancelResponse */
        AgentRunCancelResponse: {
            /** Cancellation Requested */
            cancellation_requested: boolean;
            run: components["schemas"]["AgentRun"];
        };
        /** AgentRunCreateRequest */
        AgentRunCreateRequest: {
            /** Correlation Id */
            correlation_id: string;
            /**
             * Formal
             * @default false
             */
            formal: boolean;
            /** Request Key */
            request_key: string;
        };
        /** AgentRunCreateResponse */
        AgentRunCreateResponse: {
            /** Created */
            created: boolean;
            run: components["schemas"]["AgentRun"];
        };
        /** AgentRunListResponse */
        AgentRunListResponse: {
            /** Runs */
            runs: components["schemas"]["AgentRun"][];
        };
        /** AgentRunSnapshot */
        AgentRunSnapshot: {
            /** Calls */
            calls: components["schemas"]["ModelCall"][];
            run: components["schemas"]["AgentRun"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Usage */
            usage: components["schemas"]["UsageRecord"][];
        };
        /**
         * AgentRunStatus
         * @enum {string}
         */
        AgentRunStatus: "pending" | "running" | "succeeded" | "partial_failure" | "failed" | "cancelled";
        /** AgentRunStreamRequest */
        AgentRunStreamRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Instruction */
            instruction: string;
        };
        /** Approval */
        Approval: {
            /** Decided At */
            decided_at?: string | null;
            /** Id */
            id: string;
            kind: components["schemas"]["ApprovalKind"];
            /** Project Id */
            project_id: string;
            /** Reason */
            reason?: string | null;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["ApprovalStatus"];
            /** Target Id */
            target_id: string;
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** ApprovalDecisionResponse */
        ApprovalDecisionResponse: {
            approval: components["schemas"]["Approval"];
            change_request: components["schemas"]["ChangeRequest"] | null;
            gate: components["schemas"]["QualityGateRun"];
            handoff: components["schemas"]["HandoffPacket"] | null;
        };
        /**
         * ApprovalKind
         * @enum {string}
         */
        ApprovalKind: "capability" | "quality_gate";
        /** ApprovalListResponse */
        ApprovalListResponse: {
            /** Approvals */
            approvals: components["schemas"]["Approval"][];
        };
        /**
         * ApprovalStatus
         * @enum {string}
         */
        ApprovalStatus: "pending" | "approved" | "rejected";
        /** Artifact */
        Artifact: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Project Id */
            project_id: string;
            /** Relative Path */
            relative_path: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Workflow Id */
            workflow_id: string;
        };
        /** ArtifactInventoryResponse */
        ArtifactInventoryResponse: {
            /** Artifacts */
            artifacts: components["schemas"]["Artifact"][];
            /** Versions */
            versions: components["schemas"]["ArtifactVersion"][];
        };
        /** ArtifactRef */
        ArtifactRef: {
            /** Artifact Id */
            artifact_id: string;
            content_hash: components["schemas"]["ContentHash"];
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Version */
            version: number;
        };
        /**
         * ArtifactStatus
         * @enum {string}
         */
        ArtifactStatus: "draft" | "locked" | "superseded" | "invalidated";
        /** ArtifactVersion */
        ArtifactVersion: {
            /** Artifact Id */
            artifact_id: string;
            /** Byte Size */
            byte_size: number;
            /** Checkpoint Id */
            checkpoint_id?: string | null;
            /** Content Hash */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Invalidated At */
            invalidated_at?: string | null;
            /** Invalidation Reason */
            invalidation_reason?: string | null;
            /** Locked At */
            locked_at?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id: string;
            status: components["schemas"]["ArtifactStatus"];
            /** Supersedes Id */
            supersedes_id?: string | null;
            /** Version */
            version: number;
        };
        /** ArtifactVersionCreate */
        ArtifactVersionCreate: {
            /** Correlation Id */
            correlation_id: string;
            /** Name */
            name: string;
            /** Relative Path */
            relative_path: string;
        };
        /** ArtifactVersionCreateResponse */
        ArtifactVersionCreateResponse: {
            artifact: components["schemas"]["Artifact"];
            version: components["schemas"]["ArtifactVersion"];
        };
        /** CapabilityRequest */
        CapabilityRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Changes */
            expected_changes: string;
            /**
             * Expires After Task
             * @default true
             * @constant
             */
            expires_after_task: true;
            /** Idempotency Key */
            idempotency_key: string;
            /** Project Id */
            project_id: string;
            /**
             * Proposed Command
             * @default null
             */
            proposed_command: string[] | null;
            /** Reason */
            reason: string;
            /** Request Id */
            request_id: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Requested Capability */
            requested_capability: string;
            requester_role: components["schemas"]["Stage"];
            risk_level: components["schemas"]["CapabilityRisk"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id: string;
            /**
             * Target Paths
             * @default []
             */
            target_paths: string[];
            /** Task Id */
            task_id: string;
            /** Workflow Id */
            workflow_id: string;
        };
        /** CapabilityRequestCreate */
        CapabilityRequestCreate: {
            /** Capability */
            capability: string;
            /** Command */
            command?: string[] | null;
            /** Correlation Id */
            correlation_id: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Reason */
            reason: string;
            risk_level: components["schemas"]["CapabilityRisk"];
            /**
             * Target Paths
             * @default []
             */
            target_paths: string[];
        };
        /** CapabilityRequestList */
        CapabilityRequestList: {
            /** Requests */
            requests: components["schemas"]["CapabilityRequestRecord"][];
        };
        /** CapabilityRequestRecord */
        CapabilityRequestRecord: {
            /** Capability */
            capability: string;
            /** Command */
            command?: string[] | null;
            /** Decided At */
            decided_at?: string | null;
            /** Decision Reason */
            decision_reason?: string | null;
            /** Id */
            id: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Project Id */
            project_id: string;
            /** Reason */
            reason: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Risk Level */
            risk_level: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Stage Run Id */
            stage_run_id: string;
            status: components["schemas"]["CapabilityRequestStatus"];
            /**
             * Target Paths
             * @default []
             */
            target_paths: string[];
            /** Task Id */
            task_id: string;
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * CapabilityRequestStatus
         * @enum {string}
         */
        CapabilityRequestStatus: "pending" | "approved" | "rejected" | "expired";
        /**
         * CapabilityRisk
         * @enum {string}
         */
        CapabilityRisk: "low" | "medium" | "high";
        /** CatalogResponse */
        CatalogResponse: {
            /** Tools */
            tools: components["schemas"]["ToolDefinition"][];
        };
        /** ChangeRequest */
        ChangeRequest: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Gate Run Id */
            gate_run_id?: string | null;
            /** Id */
            id: string;
            /** Input Artifact Version Ids */
            input_artifact_version_ids: string[];
            /** Project Id */
            project_id: string;
            /** Reason */
            reason: string;
            /** Resolved At */
            resolved_at?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Source Stage Run Id */
            source_stage_run_id: string;
            status: components["schemas"]["ChangeRequestStatus"];
            target_stage: components["schemas"]["Stage"];
            /** Workflow Id */
            workflow_id: string;
        };
        /** ChangeRequestCreate */
        ChangeRequestCreate: {
            /** Correlation Id */
            correlation_id: string;
            /**
             * Input Artifact Version Ids
             * @default []
             */
            input_artifact_version_ids: string[];
            /** Reason */
            reason: string;
            target_stage: components["schemas"]["Stage"];
        };
        /** ChangeRequestListResponse */
        ChangeRequestListResponse: {
            /** Change Requests */
            change_requests: components["schemas"]["ChangeRequest"][];
        };
        /**
         * ChangeRequestStatus
         * @enum {string}
         */
        ChangeRequestStatus: "open" | "resolved" | "superseded";
        /** CheckpointCreateRequest */
        CheckpointCreateRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** @default manual */
            reason: components["schemas"]["CheckpointReason"];
        };
        /** CheckpointFile */
        CheckpointFile: {
            /** Byte Size */
            byte_size: number;
            /** Content Hash */
            content_hash: string;
            /** Relative Path */
            relative_path: string;
        };
        /** CheckpointListResponse */
        CheckpointListResponse: {
            /** Checkpoints */
            checkpoints: components["schemas"]["ProjectCheckpoint"][];
        };
        /**
         * CheckpointReason
         * @enum {string}
         */
        CheckpointReason: "manual" | "pre_mutation" | "pre_restore";
        /** CheckpointRestorePlan */
        CheckpointRestorePlan: {
            /** Current Checkpoint Id */
            current_checkpoint_id: string;
            /** Overwrite Paths */
            overwrite_paths: string[];
            /** Preserved Extra Paths */
            preserved_extra_paths: string[];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Target Checkpoint Id */
            target_checkpoint_id: string;
        };
        /** CheckpointRestoreRequest */
        CheckpointRestoreRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Project Version */
            expected_project_version: number;
            /** Protection Checkpoint Id */
            protection_checkpoint_id: string;
        };
        /** CheckpointRestoreResponse */
        CheckpointRestoreResponse: {
            project: components["schemas"]["Project"];
            result: components["schemas"]["CheckpointRestoreResult"];
        };
        /** CheckpointRestoreResult */
        CheckpointRestoreResult: {
            /** Protection Checkpoint Id */
            protection_checkpoint_id: string;
            /** Restored Checkpoint Id */
            restored_checkpoint_id: string;
            /** Restored File Count */
            restored_file_count: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
        };
        /** ConflictListResponse */
        ConflictListResponse: {
            /** Conflicts */
            conflicts: components["schemas"]["FileConflict"][];
        };
        /**
         * ConflictResolution
         * @enum {string}
         */
        ConflictResolution: "keep_user" | "keep_agent" | "manual_merge";
        /** ConflictResolveRequest */
        ConflictResolveRequest: {
            /** Agent Checkpoint Id */
            agent_checkpoint_id?: string | null;
            /** Correlation Id */
            correlation_id: string;
            /** Expected Conflict Version */
            expected_conflict_version: number;
            /** Expected Project Version */
            expected_project_version: number;
            /** Merged Content Hash */
            merged_content_hash?: string | null;
            resolution: components["schemas"]["ConflictResolution"];
        };
        /** ConflictResolveResponse */
        ConflictResolveResponse: {
            conflict: components["schemas"]["FileConflict"];
            project: components["schemas"]["Project"];
            /** Protection Checkpoint Id */
            protection_checkpoint_id: string | null;
        };
        /** ContentHash */
        ContentHash: {
            /**
             * Algorithm
             * @default sha256
             * @constant
             */
            algorithm: "sha256";
            /** Digest */
            digest: string;
        };
        /** CorrelationRequest */
        CorrelationRequest: {
            /** Correlation Id */
            correlation_id: string;
        };
        /** DecisionRequest */
        DecisionRequest: {
            /** Approved */
            approved: boolean;
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason?: string | null;
        };
        /** DesktopControlResponse */
        DesktopControlResponse: {
            /**
             * Protocol Version
             * @constant
             */
            protocol_version: 1;
            /**
             * Shutdown Supported
             * @constant
             */
            shutdown_supported: true;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "shutting_down";
        };
        /**
         * ErrorCategory
         * @enum {string}
         */
        ErrorCategory: "invalid_input" | "permission" | "not_found" | "conflict" | "rate_limited" | "unavailable";
        /** EventEnvelope */
        EventEnvelope: {
            actor: components["schemas"]["ActorRef"];
            /** Causation Id */
            causation_id?: string | null;
            /** Correlation Id */
            correlation_id: string;
            /** Event Id */
            event_id?: number | null;
            /** Event Type */
            event_type: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Project Id */
            project_id?: string | null;
            /** Room Id */
            room_id?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            source: components["schemas"]["EventSource"];
            /** Task Id */
            task_id?: string | null;
            /** Workflow Id */
            workflow_id?: string | null;
        };
        /** EventReplayResponse */
        EventReplayResponse: {
            /** Events */
            events: components["schemas"]["EventEnvelope"][];
        };
        /**
         * EventSource
         * @enum {string}
         */
        EventSource: "backend" | "desktop" | "worker" | "model" | "tool";
        /** EventTicketRequest */
        EventTicketRequest: {
            /** Workflow Id */
            workflow_id: string;
        };
        /** EventTicketResponse */
        EventTicketResponse: {
            /** Expires At */
            expires_at: string;
            /** Ticket */
            ticket: string;
            /**
             * Websocket Path
             * @default /api/v1/events/ws
             * @constant
             */
            websocket_path: "/api/v1/events/ws";
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * ExecutionMode
         * @enum {string}
         */
        ExecutionMode: "manual" | "autonomous";
        /** ExternalChange */
        ExternalChange: {
            /** Baseline Content Hash */
            baseline_content_hash?: string | null;
            change_type: components["schemas"]["ExternalChangeType"];
            /** Current Content Hash */
            current_content_hash?: string | null;
            /**
             * Detected At
             * Format: date-time
             */
            detected_at: string;
            /** Id */
            id: string;
            /** Project Id */
            project_id: string;
            /** Relative Path */
            relative_path: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** @default open */
            status: components["schemas"]["ExternalChangeStatus"];
        };
        /** ExternalChangeListResponse */
        ExternalChangeListResponse: {
            /** Changes */
            changes: components["schemas"]["ExternalChange"][];
        };
        /** ExternalChangeScanRequest */
        ExternalChangeScanRequest: {
            /** Agent Checkpoint Id */
            agent_checkpoint_id?: string | null;
            /** Baseline Checkpoint Id */
            baseline_checkpoint_id: string;
            /** Correlation Id */
            correlation_id: string;
        };
        /** ExternalChangeScanResponse */
        ExternalChangeScanResponse: {
            /** Changes */
            changes: components["schemas"]["ExternalChange"][];
            /** Conflicts */
            conflicts: components["schemas"]["FileConflict"][];
            current_checkpoint: components["schemas"]["ProjectCheckpoint"];
        };
        /**
         * ExternalChangeStatus
         * @enum {string}
         */
        ExternalChangeStatus: "open" | "acknowledged";
        /**
         * ExternalChangeType
         * @enum {string}
         */
        ExternalChangeType: "added" | "modified" | "deleted";
        /** FileConflict */
        FileConflict: {
            /** Agent Content Hash */
            agent_content_hash?: string | null;
            /** Baseline Content Hash */
            baseline_content_hash?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Project Id */
            project_id: string;
            /** Relative Path */
            relative_path: string;
            resolution?: components["schemas"]["ConflictResolution"] | null;
            /** Resolved At */
            resolved_at?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** @default open */
            status: components["schemas"]["FileConflictStatus"];
            /** User Content Hash */
            user_content_hash?: string | null;
            /** Version */
            version: number;
        };
        /**
         * FileConflictStatus
         * @enum {string}
         */
        FileConflictStatus: "open" | "resolved";
        /** GateEvaluateRequest */
        GateEvaluateRequest: {
            /** Artifact Version Ids */
            artifact_version_ids: string[];
            /** Correlation Id */
            correlation_id: string;
        };
        /** GateEvaluationResponse */
        GateEvaluationResponse: {
            approval: components["schemas"]["Approval"] | null;
            change_request: components["schemas"]["ChangeRequest"] | null;
            gate: components["schemas"]["QualityGateRun"];
            handoff: components["schemas"]["HandoffPacket"] | null;
        };
        /** GateIssue */
        GateIssue: {
            /** Code */
            code: string;
            /** Details */
            details?: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
            severity: components["schemas"]["GateIssueSeverity"];
        };
        /**
         * GateIssueSeverity
         * @enum {string}
         */
        GateIssueSeverity: "warning" | "error";
        /** GateListResponse */
        GateListResponse: {
            /** Gates */
            gates: components["schemas"]["QualityGateRun"][];
        };
        /**
         * GateResolution
         * @enum {string}
         */
        GateResolution: "pending" | "approved" | "automatic" | "rewrite_required";
        /**
         * GateStatus
         * @enum {string}
         */
        GateStatus: "pass" | "warning" | "fail";
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HandoffListResponse */
        HandoffListResponse: {
            /** Handoffs */
            handoffs: components["schemas"]["HandoffPacket"][];
        };
        /** HandoffPacket */
        HandoffPacket: {
            /** Artifact Version Ids */
            artifact_version_ids: string[];
            /** Checkpoint Id */
            checkpoint_id: string;
            /** Content Hash */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            from_stage: components["schemas"]["Stage"];
            /** From Stage Run Id */
            from_stage_run_id: string;
            /** Gate Run Id */
            gate_run_id: string;
            /** Id */
            id: string;
            /** Invalidated At */
            invalidated_at?: string | null;
            /** Invalidation Reason */
            invalidation_reason?: string | null;
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["HandoffStatus"];
            to_stage: components["schemas"]["Stage"] | null;
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * HandoffStatus
         * @enum {string}
         */
        HandoffStatus: "active" | "invalidated";
        /** Message */
        Message: {
            author: components["schemas"]["MessageAuthor"];
            /** Content */
            content: string;
            /** Correction Of Id */
            correction_of_id?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            kind: components["schemas"]["MessageKind"];
            /** Room Id */
            room_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Sequence */
            sequence: number;
        };
        /** MessageAppendRequest */
        MessageAppendRequest: {
            /** Content */
            content: string;
            /** Correction Of Id */
            correction_of_id?: string | null;
            /** Correlation Id */
            correlation_id: string;
            /** Expected Room Version */
            expected_room_version: number;
        };
        /** MessageAppendResponse */
        MessageAppendResponse: {
            message: components["schemas"]["Message"];
            room: components["schemas"]["Room"];
        };
        /**
         * MessageAuthor
         * @enum {string}
         */
        MessageAuthor: "user" | "system" | "agent";
        /**
         * MessageKind
         * @enum {string}
         */
        MessageKind: "discussion" | "consultation" | "correction";
        /** MessageListResponse */
        MessageListResponse: {
            /** Messages */
            messages: components["schemas"]["Message"][];
        };
        /** ModeRequest */
        ModeRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
            mode: components["schemas"]["ExecutionMode"];
        };
        /** ModelCall */
        ModelCall: {
            /** Agent Run Id */
            agent_run_id: string;
            /** Completed At */
            completed_at?: string | null;
            /** Error Code */
            error_code?: string | null;
            /** Id */
            id: string;
            /** Output Bytes */
            output_bytes?: number | null;
            /** Output Hash */
            output_hash?: string | null;
            /** Output Ref */
            output_ref?: string | null;
            phase: components["schemas"]["ModelPhase"];
            /** Profile Id */
            profile_id: string;
            /** Prompt Hash */
            prompt_hash: string;
            role: components["schemas"]["ModelRole"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Started At */
            started_at?: string | null;
            status: components["schemas"]["ModelCallStatus"];
            /** Version */
            version: number;
        };
        /**
         * ModelCallStatus
         * @enum {string}
         */
        ModelCallStatus: "pending" | "streaming" | "succeeded" | "failed" | "cancelled";
        /**
         * ModelPhase
         * @enum {string}
         */
        ModelPhase: "p0" | "p1" | "p2r";
        /** ModelProfile */
        ModelProfile: {
            /** Base Url */
            base_url: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Credential Ref */
            credential_ref: string;
            /** Enabled */
            enabled: boolean;
            /** Id */
            id: string;
            /** Masked Hint */
            masked_hint: string;
            /** Model */
            model: string;
            /** Name */
            name: string;
            provider: components["schemas"]["ModelProvider"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** ModelProfileCreateRequest */
        ModelProfileCreateRequest: {
            /** Base Url */
            base_url: string;
            /** Correlation Id */
            correlation_id: string;
            /** Credential Ref */
            credential_ref: string;
            /** Masked Hint */
            masked_hint: string;
            /** Model */
            model: string;
            /** Name */
            name: string;
            provider: components["schemas"]["ModelProvider"];
        };
        /** ModelProfileListResponse */
        ModelProfileListResponse: {
            /** Profiles */
            profiles: components["schemas"]["ModelProfile"][];
        };
        /** ModelProfileUpdateRequest */
        ModelProfileUpdateRequest: {
            /** Base Url */
            base_url: string;
            /** Correlation Id */
            correlation_id: string;
            /** Credential Ref */
            credential_ref: string;
            /** Enabled */
            enabled: boolean;
            /** Expected Version */
            expected_version: number;
            /** Masked Hint */
            masked_hint: string;
            /** Model */
            model: string;
            /** Name */
            name: string;
            provider: components["schemas"]["ModelProvider"];
        };
        /**
         * ModelProvider
         * @enum {string}
         */
        ModelProvider: "openai_compatible" | "anthropic" | "fake";
        /**
         * ModelRole
         * @enum {string}
         */
        ModelRole: "primary" | "reviewer_a" | "reviewer_b";
        /** OrchestrationRequest */
        OrchestrationRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Instruction */
            instruction: string;
            /** Request Key */
            request_key: string;
        };
        /** PreflightCheck */
        PreflightCheck: {
            /** Code */
            code: string;
            /** Evidence */
            evidence?: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
            status: components["schemas"]["PreflightStatus"];
        };
        /** PreflightResponse */
        PreflightResponse: {
            project: components["schemas"]["Project"];
            result: components["schemas"]["ProjectPreflightResult"];
        };
        /**
         * PreflightStatus
         * @enum {string}
         */
        PreflightStatus: "pass" | "warning" | "needs_fix" | "fail";
        /** Project */
        Project: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Goal */
            goal: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["ProjectStatus"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** ProjectCheckpoint */
        ProjectCheckpoint: {
            /** Content Hash */
            content_hash: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Files */
            files: components["schemas"]["CheckpointFile"][];
            /** Id */
            id: string;
            /** Manifest Version */
            manifest_version: number;
            /** Project Id */
            project_id: string;
            reason: components["schemas"]["CheckpointReason"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Total Bytes */
            total_bytes: number;
        };
        /** ProjectCheckpointRef */
        ProjectCheckpointRef: {
            /** Checkpoint Id */
            checkpoint_id: string;
            content_hash: components["schemas"]["ContentHash"];
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
        };
        /** ProjectCommand */
        ProjectCommand: {
            /** Argv */
            argv: string[];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Timeout Seconds
             * @default 900
             */
            timeout_seconds: number;
            /** Working Directory */
            working_directory?: string | null;
        };
        /** ProjectCreateRequest */
        ProjectCreateRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Goal */
            goal: string;
            /** Local Working Directory */
            local_working_directory: string;
            /** Name */
            name: string;
            workspace_mode: components["schemas"]["WorkspaceMode"];
        };
        /** ProjectCreateResponse */
        ProjectCreateResponse: {
            manifest: components["schemas"]["ProjectManifest"];
            /**
             * Preflight Required
             * @default true
             * @constant
             */
            preflight_required: true;
            registration: components["schemas"]["ProjectRegistration"];
        };
        /** ProjectListResponse */
        ProjectListResponse: {
            /** Projects */
            projects: components["schemas"]["ProjectRegistration"][];
        };
        /** ProjectManifest */
        ProjectManifest: {
            /**
             * Build Commands
             * @default []
             */
            build_commands: components["schemas"]["ProjectCommand"][];
            /**
             * Excluded Paths
             * @default []
             */
            excluded_paths: string[];
            /**
             * Instruction Paths
             * @default []
             */
            instruction_paths: string[];
            /** Manifest Version */
            manifest_version: number;
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Source Paths
             * @default []
             */
            source_paths: string[];
            /**
             * Test Commands
             * @default []
             */
            test_commands: components["schemas"]["ProjectCommand"][];
            /**
             * Typecheck Commands
             * @default []
             */
            typecheck_commands: components["schemas"]["ProjectCommand"][];
        };
        /** ProjectMutationResponse */
        ProjectMutationResponse: {
            project: components["schemas"]["Project"];
        };
        /** ProjectPreflightResult */
        ProjectPreflightResult: {
            /** Checks */
            checks: components["schemas"]["PreflightCheck"][];
            /**
             * Completed At
             * Format: date-time
             */
            completed_at: string;
            /** Id */
            id: string;
            /** Manifest Version */
            manifest_version: number;
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["PreflightStatus"];
        };
        /** ProjectRegistration */
        ProjectRegistration: {
            project: components["schemas"]["Project"];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            workspace: components["schemas"]["Workspace"];
        };
        /**
         * ProjectStatus
         * @enum {string}
         */
        ProjectStatus: "preflight_required" | "ready" | "closed";
        /** ProjectVersionCommand */
        ProjectVersionCommand: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
        };
        /** QualityGateRun */
        QualityGateRun: {
            /** Artifact Version Ids */
            artifact_version_ids: string[];
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Id */
            id: string;
            /** Issues */
            issues: components["schemas"]["GateIssue"][];
            /** Project Id */
            project_id: string;
            resolution: components["schemas"]["GateResolution"];
            /** Resolved At */
            resolved_at?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id: string;
            status: components["schemas"]["GateStatus"];
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** RecoveryListResponse */
        RecoveryListResponse: {
            /** Recoveries */
            recoveries: components["schemas"]["RecoveryRecord"][];
        };
        /** RecoveryRecord */
        RecoveryRecord: {
            /**
             * Detected At
             * Format: date-time
             */
            detected_at: string;
            /** Id */
            id: string;
            /** Interrupted Agent Runs */
            interrupted_agent_runs: number;
            /** Interrupted Tasks */
            interrupted_tasks: number;
            /** Interrupted Tool Calls */
            interrupted_tool_calls: number;
            /** Project Id */
            project_id: string;
            /** Resolved At */
            resolved_at?: string | null;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id?: string | null;
            status: components["schemas"]["RecoveryStatus"];
            /** Workflow Id */
            workflow_id: string;
        };
        /**
         * RecoveryStatus
         * @enum {string}
         */
        RecoveryStatus: "pending" | "resumed" | "discarded";
        /** RestorePlanRequest */
        RestorePlanRequest: {
            /** Correlation Id */
            correlation_id: string;
        };
        /** RestorePlanResponse */
        RestorePlanResponse: {
            plan: components["schemas"]["CheckpointRestorePlan"];
            protection_checkpoint: components["schemas"]["ProjectCheckpoint"];
        };
        /** RoleCard */
        RoleCard: {
            /** Content */
            content: string;
            /** Content Hash */
            content_hash: string;
            /** Display Name */
            display_name: string;
            /**
             * Language
             * @constant
             */
            language: "zh-CN";
            /** Role Card Version */
            role_card_version: string;
            role_id: components["schemas"]["Stage"];
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version: 1;
            stage_id: components["schemas"]["Stage"];
        };
        /** Room */
        Room: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Next Sequence */
            next_sequence: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Stage Run Id */
            stage_run_id: string;
            status: components["schemas"]["RoomStatus"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** RoomAssignmentRequest */
        RoomAssignmentRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version?: number | null;
            /** Primary Profile Id */
            primary_profile_id: string;
            /** Reviewer A Profile Id */
            reviewer_a_profile_id?: string | null;
            /** Reviewer B Profile Id */
            reviewer_b_profile_id?: string | null;
        };
        /** RoomModelAssignment */
        RoomModelAssignment: {
            /** Primary Profile Id */
            primary_profile_id: string;
            /** Reviewer A Profile Id */
            reviewer_a_profile_id?: string | null;
            /** Reviewer B Profile Id */
            reviewer_b_profile_id?: string | null;
            /** Room Id */
            room_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /**
         * RoomStatus
         * @enum {string}
         */
        RoomStatus: "active" | "consultation" | "archived";
        /** ShutdownResponse */
        ShutdownResponse: {
            /**
             * Status
             * @enum {string}
             */
            status: "accepted" | "already_requested";
        };
        /**
         * Stage
         * @enum {string}
         */
        Stage: "planner" | "designer" | "builder" | "reviewer" | "deployer";
        /** StageContract */
        StageContract: {
            /** Contract Version */
            contract_version: string;
            /** Default Capabilities */
            default_capabilities: string[];
            /** Forbidden Capabilities */
            forbidden_capabilities: string[];
            initial_state: components["schemas"]["StageRunState"];
            path_policy: components["schemas"]["StagePathPolicy"];
            /** Requestable Capabilities */
            requestable_capabilities: string[];
            /** Role Card Version */
            role_card_version: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
        };
        /** StagePathPolicy */
        StagePathPolicy: {
            /** Delete Scopes */
            delete_scopes: components["schemas"]["StagePathScope"][];
            /** Read Scopes */
            read_scopes: components["schemas"]["StagePathScope"][];
            /** Write Scopes */
            write_scopes: components["schemas"]["StagePathScope"][];
        };
        /**
         * StagePathScope
         * @enum {string}
         */
        StagePathScope: "project_non_sensitive" | "planner_artifact" | "designer_artifact" | "builder_artifact" | "reviewer_artifact" | "deployer_artifact" | "project_source" | "project_test" | "project_build_config" | "generated" | "deployment_config" | "deployment_script" | "stage_draft";
        /** StageRun */
        StageRun: {
            /** Attempt */
            attempt: number;
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Started At */
            started_at?: string | null;
            state: components["schemas"]["StageRunState"];
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** StageRunHistoryResponse */
        StageRunHistoryResponse: {
            /** Stage Runs */
            stage_runs: components["schemas"]["StageRun"][];
        };
        /**
         * StageRunState
         * @enum {string}
         */
        StageRunState: "locked" | "ready" | "discussing" | "producing" | "p2r_reviewing" | "quality_checking" | "waiting_approval" | "handoff_ready" | "completed" | "warning_blocked" | "needs_fix" | "external_conflict" | "interrupted" | "failed" | "cancelled" | "abandoned";
        /** StageTransitionRequest */
        StageTransitionRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Stage Version */
            expected_stage_version: number;
            /** Expected Workflow Version */
            expected_workflow_version: number;
            target_state: components["schemas"]["StageRunState"];
        };
        /** StageTransitionResponse */
        StageTransitionResponse: {
            stage_run: components["schemas"]["StageRun"];
            unlocked_stage_run: components["schemas"]["StageRun"] | null;
            workflow: components["schemas"]["Workflow"];
        };
        /** SystemInfoResponse */
        SystemInfoResponse: {
            /** Backend Version */
            backend_version: string;
            /**
             * Protocol Version
             * @constant
             */
            protocol_version: 1;
        };
        /** TaskCompleteRequest */
        TaskCompleteRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
            /** Result */
            result?: {
                [key: string]: unknown;
            };
            /** Succeeded */
            succeeded: boolean;
        };
        /** TaskCreateRequest */
        TaskCreateRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Payload */
            payload?: {
                [key: string]: unknown;
            };
            /** Title */
            title: string;
        };
        /** TaskListResponse */
        TaskListResponse: {
            /** Tasks */
            tasks: components["schemas"]["WorkflowTask"][];
        };
        /**
         * TaskStatus
         * @enum {string}
         */
        TaskStatus: "queued" | "running" | "succeeded" | "failed" | "cancelled";
        /** TaskVersionRequest */
        TaskVersionRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
        };
        /** ToolCall */
        ToolCall: {
            /** Arguments Hash */
            arguments_hash: string;
            /** Capability */
            capability: string;
            /** Capability Request Id */
            capability_request_id?: string | null;
            /** Completed At */
            completed_at?: string | null;
            /** Error Code */
            error_code?: string | null;
            /** Id */
            id: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Project Id */
            project_id: string;
            /** Result */
            result?: {
                [key: string]: unknown;
            };
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["ToolCallStatus"];
            /** Task Id */
            task_id: string;
            /** Tool Name */
            tool_name: string;
            /** Workflow Id */
            workflow_id: string;
        };
        /** ToolCallList */
        ToolCallList: {
            /** Calls */
            calls: components["schemas"]["ToolCall"][];
        };
        /**
         * ToolCallStatus
         * @enum {string}
         */
        ToolCallStatus: "running" | "succeeded" | "failed" | "cancelled" | "timed_out" | "interrupted";
        /** ToolDefinition */
        ToolDefinition: {
            /**
             * Allowed Scopes
             * @default []
             */
            allowed_scopes: components["schemas"]["StagePathScope"][];
            /** Capability */
            capability: string;
            /** Max Timeout Seconds */
            max_timeout_seconds: number;
            /** Mutating */
            mutating: boolean;
            /** Name */
            name: string;
            operation: components["schemas"]["ToolOperation"];
        };
        /** ToolExecuteRequest */
        ToolExecuteRequest: {
            /** Arguments */
            arguments?: {
                [key: string]: unknown;
            };
            /** Correlation Id */
            correlation_id: string;
            /** Idempotency Key */
            idempotency_key: string;
            /**
             * Timeout Seconds
             * @default 900
             */
            timeout_seconds: number;
            /** Tool Name */
            tool_name: string;
        };
        /** ToolExecutionRequest */
        ToolExecutionRequest: {
            actor: components["schemas"]["ActorRef"];
            /** Arguments */
            arguments?: {
                [key: string]: unknown;
            };
            /**
             * Causation Id
             * @default null
             */
            causation_id: string | null;
            /** Correlation Id */
            correlation_id: string;
            /** Idempotency Key */
            idempotency_key: string;
            /** Project Id */
            project_id: string;
            /** Request Id */
            request_id: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Required Capability */
            required_capability: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            stage: components["schemas"]["Stage"];
            /** Stage Run Id */
            stage_run_id: string;
            /** Task Id */
            task_id: string;
            /** Timeout Seconds */
            timeout_seconds: number;
            /** Tool Name */
            tool_name: string;
            /** Workflow Id */
            workflow_id: string;
        };
        /** ToolExecutionResponse */
        ToolExecutionResponse: {
            call: components["schemas"]["ToolCall"];
            /** Output */
            output: {
                [key: string]: unknown;
            };
        };
        /**
         * ToolExecutionStatus
         * @enum {string}
         */
        ToolExecutionStatus: "succeeded" | "failed" | "cancelled" | "timed_out";
        /** ToolFailure */
        ToolFailure: {
            category: components["schemas"]["ErrorCategory"];
            /** Code */
            code: string;
            /** Details */
            details?: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
            /**
             * Retryable
             * @default false
             */
            retryable: boolean;
        };
        /**
         * ToolOperation
         * @enum {string}
         */
        ToolOperation: "read" | "write" | "delete" | "create_directory" | "command";
        /** ToolResult */
        ToolResult: {
            /**
             * Completed At
             * Format: date-time
             */
            completed_at: string;
            /** @default null */
            failure: components["schemas"]["ToolFailure"] | null;
            /** Idempotency Key */
            idempotency_key: string;
            /** Output */
            output?: {
                [key: string]: unknown;
            };
            /** Request Id */
            request_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            status: components["schemas"]["ToolExecutionStatus"];
        };
        /** UsageRecord */
        UsageRecord: {
            /** Input Tokens */
            input_tokens: number;
            /** Model Call Id */
            model_call_id: string;
            /** Output Tokens */
            output_tokens: number;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Total Tokens */
            total_tokens: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** Workflow */
        Workflow: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            current_stage: components["schemas"]["Stage"];
            execution_mode: components["schemas"]["ExecutionMode"];
            /** Id */
            id: string;
            /** Project Id */
            project_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            status: components["schemas"]["WorkflowStatus"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** WorkflowControlRequest */
        WorkflowControlRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
        };
        /** WorkflowCreateRequest */
        WorkflowCreateRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Title */
            title: string;
        };
        /** WorkflowListResponse */
        WorkflowListResponse: {
            /** Workflows */
            workflows: components["schemas"]["Workflow"][];
        };
        /** WorkflowSnapshot */
        WorkflowSnapshot: {
            /** Rooms */
            rooms: components["schemas"]["Room"][];
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Runs */
            stage_runs: components["schemas"]["StageRun"][];
            workflow: components["schemas"]["Workflow"];
        };
        /**
         * WorkflowStatus
         * @enum {string}
         */
        WorkflowStatus: "created" | "preflight_failed" | "running" | "waiting_user" | "warning_blocked" | "paused" | "external_conflict" | "interrupted" | "failed" | "stopped" | "abandoned" | "completed";
        /** WorkflowTask */
        WorkflowTask: {
            /** Completed At */
            completed_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Payload */
            payload?: {
                [key: string]: unknown;
            };
            /** Result */
            result?: {
                [key: string]: unknown;
            } | null;
            /** Room Id */
            room_id: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
            /** Stage Run Id */
            stage_run_id: string;
            /** Started At */
            started_at?: string | null;
            status: components["schemas"]["TaskStatus"];
            /** Title */
            title: string;
            /** Version */
            version: number;
            /** Workflow Id */
            workflow_id: string;
        };
        /** WorkflowVersionRequest */
        WorkflowVersionRequest: {
            /** Correlation Id */
            correlation_id: string;
            /** Expected Version */
            expected_version: number;
        };
        /** Workspace */
        Workspace: {
            /** Canonical Root Path */
            canonical_root_path: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            mode: components["schemas"]["WorkspaceMode"];
            /** Project Id */
            project_id: string;
            /** Root Path */
            root_path: string;
            /**
             * Schema Version
             * @constant
             */
            schema_version: 1;
        };
        /**
         * WorkspaceMode
         * @enum {string}
         */
        WorkspaceMode: "managed" | "direct";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    get_agent_run_api_v1_agent_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentRunSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_agent_run_api_v1_agent_runs__run_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentRunCancelResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_agent_run_output_api_v1_agent_runs__run_id__output_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_agent_run_api_v1_agent_runs__run_id__stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AgentRunStreamRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_gate_approval_api_v1_approvals__approval_id__decision_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                approval_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalDecisionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_capability_api_v1_capability_requests__request_id__decision_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CapabilityRequestRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replay_events_api_v1_events_replay_get: {
        parameters: {
            query: {
                workflow_id: string;
                after_event_id?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventReplayResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    issue_event_ticket_api_v1_events_tickets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventTicketRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventTicketResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: "ok";
                    };
                };
            };
        };
    };
    list_profiles_api_v1_model_profiles_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfileListResponse"];
                };
            };
        };
    };
    create_profile_api_v1_model_profiles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelProfileCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfile"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_profile_api_v1_model_profiles__profile_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfile"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_profile_api_v1_model_profiles__profile_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                profile_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelProfileUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelProfile"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_api_v1_projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectListResponse"];
                };
            };
        };
    };
    create_project_api_v1_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_api_v1_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectRegistration"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_checkpoints_api_v1_projects__project_id__checkpoints_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckpointListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_checkpoint_api_v1_projects__project_id__checkpoints_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckpointCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectCheckpoint"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    restore_checkpoint_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                checkpoint_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckpointRestoreRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CheckpointRestoreResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    plan_restore_api_v1_projects__project_id__checkpoints__checkpoint_id__restore_plan_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                checkpoint_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestorePlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RestorePlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    close_project_api_v1_projects__project_id__close_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectVersionCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMutationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_conflicts_api_v1_projects__project_id__conflicts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConflictListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_conflict_api_v1_projects__project_id__conflicts__conflict_id__resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                conflict_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConflictResolveRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConflictResolveResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_external_changes_api_v1_projects__project_id__external_changes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExternalChangeListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    scan_external_changes_api_v1_projects__project_id__external_changes_scan_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExternalChangeScanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExternalChangeScanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    open_project_api_v1_projects__project_id__open_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectVersionCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectRegistration"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_preflight_api_v1_projects__project_id__preflight_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectPreflightResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_preflight_api_v1_projects__project_id__preflight_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectVersionCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreflightResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_workflows_api_v1_projects__project_id__workflows_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_workflow_api_v1_projects__project_id__workflows_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    readiness_api_v1_readiness_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: "ready";
                    };
                };
            };
        };
    };
    list_recoveries_api_v1_recovery_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryListResponse"];
                };
            };
        };
    };
    resolve_recovery_api_v1_recovery__recovery_id___action__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                recovery_id: string;
                action: "resume" | "discard";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_agent_runs_api_v1_rooms__room_id__agent_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentRunListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_agent_run_api_v1_rooms__room_id__agent_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AgentRunCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentRunCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_messages_api_v1_rooms__room_id__messages_get: {
        parameters: {
            query?: {
                after_sequence?: number;
                limit?: number;
            };
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    append_message_api_v1_rooms__room_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageAppendRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageAppendResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_room_assignment_api_v1_rooms__room_id__model_assignment_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomModelAssignment"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    assign_room_models_api_v1_rooms__room_id__model_assignment_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoomAssignmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoomModelAssignment"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    enqueue_task_api_v1_rooms__room_id__tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                room_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowTask"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_artifact_version_api_v1_stage_runs__stage_run_id__artifact_versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stage_run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArtifactVersionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactVersionCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    evaluate_quality_gate_api_v1_stage_runs__stage_run_id__quality_gates_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stage_run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GateEvaluateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GateEvaluationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    desktop_control_api_v1_system_control_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DesktopControlResponse"];
                };
            };
        };
    };
    system_info_api_v1_system_info_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemInfoResponse"];
                };
            };
        };
    };
    request_shutdown_api_v1_system_shutdown_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShutdownResponse"];
                };
            };
        };
    };
    cancel_task_api_v1_tasks__task_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowTask"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    request_capability_api_v1_tasks__task_id__capability_requests_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CapabilityRequestCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CapabilityRequestRecord"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    complete_task_api_v1_tasks__task_id__complete_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskCompleteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowTask"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_task_api_v1_tasks__task_id__start_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaskVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowTask"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    execute_tool_api_v1_tasks__task_id__tool_calls_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToolExecuteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolExecutionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_tool_call_api_v1_tool_calls__call_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                call_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCall"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_tool_catalog_api_v1_tools_catalog_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogResponse"];
                };
            };
        };
    };
    get_workflow_api_v1_workflows__workflow_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_approvals_api_v1_workflows__workflow_id__approvals_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["ApprovalStatus"] | null;
            };
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_artifacts_api_v1_workflows__workflow_id__artifacts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactInventoryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_capability_requests_api_v1_workflows__workflow_id__capability_requests_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["CapabilityRequestStatus"] | null;
            };
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CapabilityRequestList"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_change_requests_api_v1_workflows__workflow_id__change_requests_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeRequestListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_change_request_api_v1_workflows__workflow_id__change_requests_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeRequestCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeRequest"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_handoffs_api_v1_workflows__workflow_id__handoffs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandoffListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_workflow_mode_api_v1_workflows__workflow_id__mode_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workflow"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    orchestrate_workflow_stage_api_v1_workflows__workflow_id__orchestration_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrchestrationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_quality_gates_api_v1_workflows__workflow_id__quality_gates_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GateListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_stage_history_api_v1_workflows__workflow_id__stage_runs_history_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StageRunHistoryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reopen_stage_api_v1_workflows__workflow_id__stages__stage__reopen_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
                stage: components["schemas"]["Stage"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    transition_stage_api_v1_workflows__workflow_id__stages__stage__transition_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
                stage: components["schemas"]["Stage"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StageTransitionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StageTransitionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_workflow_api_v1_workflows__workflow_id__start_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowSnapshot"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_tasks_api_v1_workflows__workflow_id__tasks_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["TaskStatus"] | null;
            };
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_tool_calls_api_v1_workflows__workflow_id__tool_calls_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCallList"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    control_workflow_api_v1_workflows__workflow_id___action__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
                action: "pause" | "resume" | "stop" | "abandon";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowControlRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Workflow"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
