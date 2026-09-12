export interface paths {
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/phone/challenges": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Phone Challenge */
        post: operations["create_phone_challenge_api_v1_auth_phone_challenges_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/phone/challenges/{challenge_id}/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Verify Phone Challenge */
        post: operations["verify_phone_challenge_api_v1_auth_phone_challenges__challenge_id__verify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Register */
        post: operations["register_api_v1_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Summary */
        get: operations["get_summary_api_v1_billing_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Usage */
        get: operations["get_usage_api_v1_billing_usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/usage/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Task Usage */
        get: operations["get_task_usage_api_v1_billing_usage_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chapters/{chapter_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Chapter */
        get: operations["get_chapter_api_v1_chapters__chapter_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Chapter */
        patch: operations["update_chapter_api_v1_chapters__chapter_id__patch"];
        trace?: never;
    };
    "/api/v1/chapters/{chapter_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Chapter Progress */
        put: operations["update_chapter_progress_api_v1_chapters__chapter_id__progress_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chapters/{chapter_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Chapter Status */
        patch: operations["update_chapter_status_api_v1_chapters__chapter_id__status_patch"];
        trace?: never;
    };
    "/api/v1/dashboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Dashboard */
        get: operations["get_dashboard_api_v1_dashboard_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/debug/workflow-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Workflow Runs */
        get: operations["list_workflow_runs_api_v1_debug_workflow_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/debug/workflow-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workflow Run */
        get: operations["get_workflow_run_api_v1_debug_workflow_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Live */
        get: operations["live_api_v1_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["ready_api_v1_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Novels */
        get: operations["list_novels_api_v1_novels_get"];
        put?: never;
        /** Create Novel */
        post: operations["create_novel_api_v1_novels_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Novel */
        get: operations["get_novel_api_v1_novels__novel_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/applied-style": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Apply Style */
        patch: operations["apply_style_api_v1_novels__novel_id__applied_style_patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/chapters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Chapters */
        get: operations["list_chapters_api_v1_novels__novel_id__chapters_get"];
        put?: never;
        /** Create Chapter */
        post: operations["create_chapter_api_v1_novels__novel_id__chapters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Characters */
        get: operations["list_characters_api_v1_novels__novel_id__characters_get"];
        put?: never;
        /** Create Character */
        post: operations["create_character_api_v1_novels__novel_id__characters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/characters/{character_id}/experiences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Experiences */
        get: operations["list_experiences_api_v1_novels__novel_id__characters__character_id__experiences_get"];
        put?: never;
        /** Create Experience */
        post: operations["create_experience_api_v1_novels__novel_id__characters__character_id__experiences_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/characters/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Character */
        delete: operations["delete_character_api_v1_novels__novel_id__characters__entity_id__delete"];
        options?: never;
        head?: never;
        /** Update Character */
        patch: operations["update_character_api_v1_novels__novel_id__characters__entity_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/experiences/{experience_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Experience */
        delete: operations["delete_experience_api_v1_novels__novel_id__experiences__experience_id__delete"];
        options?: never;
        head?: never;
        /** Update Experience */
        patch: operations["update_experience_api_v1_novels__novel_id__experiences__experience_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/factions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Factions */
        get: operations["list_factions_api_v1_novels__novel_id__factions_get"];
        put?: never;
        /** Create Faction */
        post: operations["create_faction_api_v1_novels__novel_id__factions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/factions/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Faction */
        delete: operations["delete_faction_api_v1_novels__novel_id__factions__entity_id__delete"];
        options?: never;
        head?: never;
        /** Update Faction */
        patch: operations["update_faction_api_v1_novels__novel_id__factions__entity_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/foreshadowings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Foreshadowings */
        get: operations["list_foreshadowings_api_v1_novels__novel_id__foreshadowings_get"];
        put?: never;
        /** Create Foreshadowing */
        post: operations["create_foreshadowing_api_v1_novels__novel_id__foreshadowings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/foreshadowings/{foreshadowing_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Foreshadowing */
        delete: operations["delete_foreshadowing_api_v1_novels__novel_id__foreshadowings__foreshadowing_id__delete"];
        options?: never;
        head?: never;
        /** Update Foreshadowing */
        patch: operations["update_foreshadowing_api_v1_novels__novel_id__foreshadowings__foreshadowing_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/glossary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Glossary */
        get: operations["list_glossary_api_v1_novels__novel_id__glossary_get"];
        put?: never;
        /** Create Glossary */
        post: operations["create_glossary_api_v1_novels__novel_id__glossary_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/glossary/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Glossary */
        delete: operations["delete_glossary_api_v1_novels__novel_id__glossary__entity_id__delete"];
        options?: never;
        head?: never;
        /** Update Glossary */
        patch: operations["update_glossary_api_v1_novels__novel_id__glossary__entity_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Items */
        get: operations["list_items_api_v1_novels__novel_id__items_get"];
        put?: never;
        /** Create Item */
        post: operations["create_item_api_v1_novels__novel_id__items_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/items/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Item */
        delete: operations["delete_item_api_v1_novels__novel_id__items__entity_id__delete"];
        options?: never;
        head?: never;
        /** Update Item */
        patch: operations["update_item_api_v1_novels__novel_id__items__entity_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/locations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Locations */
        get: operations["list_locations_api_v1_novels__novel_id__locations_get"];
        put?: never;
        /** Create Location */
        post: operations["create_location_api_v1_novels__novel_id__locations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/locations/{entity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Location */
        delete: operations["delete_location_api_v1_novels__novel_id__locations__entity_id__delete"];
        options?: never;
        head?: never;
        /** Update Location */
        patch: operations["update_location_api_v1_novels__novel_id__locations__entity_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/outline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Outline */
        put: operations["save_outline_api_v1_novels__novel_id__outline_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/outline-nodes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Nodes */
        get: operations["list_nodes_api_v1_novels__novel_id__outline_nodes_get"];
        put?: never;
        /** Create Node */
        post: operations["create_node_api_v1_novels__novel_id__outline_nodes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/outline-nodes/{node_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Node */
        delete: operations["delete_node_api_v1_novels__novel_id__outline_nodes__node_id__delete"];
        options?: never;
        head?: never;
        /** Update Node */
        patch: operations["update_node_api_v1_novels__novel_id__outline_nodes__node_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/plot-progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Plot */
        put: operations["save_plot_api_v1_novels__novel_id__plot_progress_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List References */
        get: operations["list_references_api_v1_novels__novel_id__references_get"];
        put?: never;
        /** Create Reference */
        post: operations["create_reference_api_v1_novels__novel_id__references_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/references/{reference_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Reference */
        delete: operations["delete_reference_api_v1_novels__novel_id__references__reference_id__delete"];
        options?: never;
        head?: never;
        /** Update Reference */
        patch: operations["update_reference_api_v1_novels__novel_id__references__reference_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/references/{reference_id}/reindex": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reindex Reference */
        post: operations["reindex_reference_api_v1_novels__novel_id__references__reference_id__reindex_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/references/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Search References */
        post: operations["search_references_api_v1_novels__novel_id__references_search_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/relations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Relations */
        get: operations["list_relations_api_v1_novels__novel_id__relations_get"];
        put?: never;
        /** Create Relation */
        post: operations["create_relation_api_v1_novels__novel_id__relations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/relations/{relation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Relation */
        delete: operations["delete_relation_api_v1_novels__novel_id__relations__relation_id__delete"];
        options?: never;
        head?: never;
        /** Update Relation */
        patch: operations["update_relation_api_v1_novels__novel_id__relations__relation_id__patch"];
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/story-background": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Story Background */
        put: operations["save_story_background_api_v1_novels__novel_id__story_background_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/story-progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Story Progress */
        put: operations["save_story_progress_api_v1_novels__novel_id__story_progress_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Novel Summary */
        put: operations["update_novel_summary_api_v1_novels__novel_id__summary_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/version-diff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version Diff */
        get: operations["get_version_diff_api_v1_novels__novel_id__version_diff_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Versions */
        get: operations["list_versions_api_v1_novels__novel_id__versions_get"];
        put?: never;
        /** Submit Manual Version */
        post: operations["submit_manual_version_api_v1_novels__novel_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version */
        get: operations["get_version_api_v1_novels__novel_id__versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/versions/{version_id}/adopt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Adopt Candidate Version */
        post: operations["adopt_candidate_version_api_v1_novels__novel_id__versions__version_id__adopt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/versions/{version_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Historical Version */
        post: operations["restore_historical_version_api_v1_novels__novel_id__versions__version_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/versions/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Version */
        post: operations["preview_version_api_v1_novels__novel_id__versions_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/workspace": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workspace */
        get: operations["get_workspace_api_v1_novels__novel_id__workspace_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/workspace/bootstrap": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workspace Bootstrap */
        get: operations["get_workspace_bootstrap_api_v1_novels__novel_id__workspace_bootstrap_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/workspace/lore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workspace Lore */
        get: operations["get_workspace_lore_api_v1_novels__novel_id__workspace_lore_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/workspace/planning": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workspace Planning */
        get: operations["get_workspace_planning_api_v1_novels__novel_id__workspace_planning_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/workspace/resources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workspace Resources */
        get: operations["get_workspace_resources_api_v1_novels__novel_id__workspace_resources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/world-setting": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save World Setting */
        put: operations["save_world_setting_api_v1_novels__novel_id__world_setting_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/novels/{novel_id}/writing-bible": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Writing Bible */
        put: operations["save_writing_bible_api_v1_novels__novel_id__writing_bible_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/portrait-tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Portrait Task */
        get: operations["get_portrait_task_api_v1_portrait_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/quality-checks/{check_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Quality Check */
        get: operations["get_quality_check_api_v1_quality_checks__check_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Quality Check */
        patch: operations["update_quality_check_api_v1_quality_checks__check_id__patch"];
        trace?: never;
    };
    "/api/v1/quality-checks/{check_id}/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Quality Check */
        post: operations["run_quality_check_api_v1_quality_checks__check_id__run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifact-summaries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Review Artifact Summaries */
        get: operations["list_review_artifact_summaries_api_v1_review_artifact_summaries_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Review Artifacts */
        get: operations["list_review_artifacts_api_v1_review_artifacts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Review Artifact */
        get: operations["get_review_artifact_api_v1_review_artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts/{artifact_id}/decision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Review Artifact */
        post: operations["decide_review_artifact_api_v1_review_artifacts__artifact_id__decision_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Styles */
        get: operations["list_styles_api_v1_styles_get"];
        put?: never;
        /** Create Style */
        post: operations["create_style_api_v1_styles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles/{style_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Style */
        delete: operations["delete_style_api_v1_styles__style_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles/{style_id}/portrait": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Portrait */
        post: operations["create_portrait_api_v1_styles__style_id__portrait_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles/{style_id}/references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Reference */
        post: operations["upload_reference_api_v1_styles__style_id__references_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles/{style_id}/references/{reference_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Reference */
        delete: operations["delete_reference_api_v1_styles__style_id__references__reference_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/styles/{style_id}/sections/{section}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Section */
        patch: operations["update_section_api_v1_styles__style_id__sections__section__patch"];
        trace?: never;
    };
    "/api/v1/styles/{style_id}/sections/{section}/portrait": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Section Portrait */
        post: operations["create_section_portrait_api_v1_styles__style_id__sections__section__portrait_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/assets/{asset_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Asset
         * @description 经过小说归属校验后返回素材内容。
         */
        get: operations["download_asset_api_v1_video_assets__asset_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/assets/{asset_id}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Preview Asset
         * @description 经过归属校验后以内联响应预览视觉设定图片。
         */
        get: operations["preview_asset_api_v1_video_assets__asset_id__preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/assets/{asset_id}/rights": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Confirm Asset
         * @description 确认或拒绝素材权利；只有 confirmed 会锁定素材。
         */
        patch: operations["confirm_asset_api_v1_video_assets__asset_id__rights_patch"];
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode */
        get: operations["get_video_episode_api_v1_video_episodes__episode_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Video Episode */
        patch: operations["update_video_episode_api_v1_video_episodes__episode_id__patch"];
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/commands/{client_request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Command */
        get: operations["get_video_episode_command_api_v1_video_episodes__episode_id__commands__client_request_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/impact-reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Impact Reviews */
        get: operations["list_video_impact_reviews_api_v1_video_episodes__episode_id__impact_reviews_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Impact Review */
        get: operations["get_video_impact_review_api_v1_video_episodes__episode_id__impact_reviews__review_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/impact-reviews/{review_id}/decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Video Impact Review */
        post: operations["decide_video_impact_review_api_v1_video_episodes__episode_id__impact_reviews__review_id__decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Production Baselines */
        get: operations["list_video_production_baselines_api_v1_video_episodes__episode_id__production_baselines_get"];
        put?: never;
        /** Create Video Production Baseline */
        post: operations["create_video_production_baseline_api_v1_video_episodes__episode_id__production_baselines_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Production Baseline */
        get: operations["get_video_production_baseline_api_v1_video_episodes__episode_id__production_baselines__baseline_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Episode Edit Versions */
        get: operations["list_video_episode_edit_versions_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions_get"];
        put?: never;
        /** Create Video Episode Edit Version */
        post: operations["create_video_episode_edit_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Edit Version */
        get: operations["get_video_episode_edit_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Video Episode Export */
        post: operations["start_video_episode_export_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Export Task */
        get: operations["get_video_episode_export_task_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Video Episode Export */
        post: operations["retry_video_episode_export_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks__task_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Delivery */
        get: operations["get_video_episode_delivery_api_v1_video_episodes__episode_id__production_baselines__baseline_id__exports__export_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Delivery Content */
        get: operations["get_video_episode_delivery_content_api_v1_video_episodes__episode_id__production_baselines__baseline_id__exports__export_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Episode Mix Versions */
        get: operations["list_video_episode_mix_versions_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions_get"];
        put?: never;
        /** Create Video Episode Mix Version */
        post: operations["create_video_episode_mix_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Mix Version */
        get: operations["get_video_episode_mix_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/production-baselines/{baseline_id}/shots/{shot_id}/render-tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Video Episode Shot Render */
        post: operations["start_video_episode_shot_render_api_v1_video_episodes__episode_id__production_baselines__baseline_id__shots__shot_id__render_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Render Task */
        get: operations["get_video_episode_render_task_api_v1_video_episodes__episode_id__render_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/render-tasks/{task_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Video Episode Render Task */
        post: operations["retry_video_episode_render_task_api_v1_video_episodes__episode_id__render_tasks__task_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/candidates/{artifact_id}/adopt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Adopt Video Episode Script Candidate */
        post: operations["adopt_video_episode_script_candidate_api_v1_video_episodes__episode_id__script_candidates__artifact_id__adopt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/confirmations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Prepare Video Episode Script Confirmation */
        post: operations["prepare_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Script Confirmation */
        get: operations["get_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Video Episode Script Confirmation */
        post: operations["approve_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations__artifact_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Script Draft */
        get: operations["get_video_episode_script_draft_api_v1_video_episodes__episode_id__script_draft_get"];
        /** Save Video Episode Script Draft */
        put: operations["save_video_episode_script_draft_api_v1_video_episodes__episode_id__script_draft_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Video Episode Script Run */
        post: operations["start_video_episode_script_run_api_v1_video_episodes__episode_id__script_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Script Run */
        get: operations["get_video_episode_script_run_api_v1_video_episodes__episode_id__script_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Episode Script Versions */
        get: operations["list_video_episode_script_versions_api_v1_video_episodes__episode_id__script_versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/script/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Script Version */
        get: operations["get_video_episode_script_version_api_v1_video_episodes__episode_id__script_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/source-sets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Episode Source Sets */
        get: operations["list_video_episode_source_sets_api_v1_video_episodes__episode_id__source_sets_get"];
        put?: never;
        /** Create Video Episode Source Set */
        post: operations["create_video_episode_source_set_api_v1_video_episodes__episode_id__source_sets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/source-sets/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Source Set */
        get: operations["get_video_episode_source_set_api_v1_video_episodes__episode_id__source_sets__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Storyboard Candidate */
        get: operations["get_video_storyboard_candidate_api_v1_video_episodes__episode_id__storyboard_candidates__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/candidates/{artifact_id}/adopt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Adopt Video Storyboard Candidate */
        post: operations["adopt_video_storyboard_candidate_api_v1_video_episodes__episode_id__storyboard_candidates__artifact_id__adopt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Prepare Video Storyboard Confirmation */
        post: operations["prepare_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Storyboard Confirmation */
        get: operations["get_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/confirmations/{artifact_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Video Storyboard Confirmation */
        post: operations["approve_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations__artifact_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Storyboard Draft */
        get: operations["get_video_storyboard_draft_api_v1_video_episodes__episode_id__storyboard_draft_get"];
        /** Save Video Storyboard Draft */
        put: operations["save_video_storyboard_draft_api_v1_video_episodes__episode_id__storyboard_draft_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Storyboard Runs */
        get: operations["list_video_storyboard_runs_api_v1_video_episodes__episode_id__storyboard_runs_get"];
        put?: never;
        /** Start Video Storyboard Run */
        post: operations["start_video_storyboard_run_api_v1_video_episodes__episode_id__storyboard_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Storyboard Run */
        get: operations["get_video_storyboard_run_api_v1_video_episodes__episode_id__storyboard_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Storyboard Versions */
        get: operations["list_video_storyboard_versions_api_v1_video_episodes__episode_id__storyboard_versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/storyboard/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Storyboard Version */
        get: operations["get_video_storyboard_version_api_v1_video_episodes__episode_id__storyboard_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/take-adoptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Video Take Adoption */
        post: operations["create_video_take_adoption_api_v1_video_episodes__episode_id__take_adoptions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/take-adoptions/{adoption_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Take Adoption */
        get: operations["get_video_take_adoption_api_v1_video_episodes__episode_id__take_adoptions__adoption_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/takes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Take Candidates */
        get: operations["list_video_take_candidates_api_v1_video_episodes__episode_id__takes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/episodes/{episode_id}/takes/{take_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Episode Take Content */
        get: operations["get_video_episode_take_content_api_v1_video_episodes__episode_id__takes__take_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/novels/{novel_id}/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Projects
         * @description 列出当前小说的视频项目。
         */
        get: operations["list_projects_api_v1_video_novels__novel_id__projects_get"];
        put?: never;
        /**
         * Create Project
         * @description 为当前小说创建视频项目。
         */
        post: operations["create_project_api_v1_video_novels__novel_id__projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/production-capabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Production Capabilities */
        get: operations["get_video_production_capabilities_api_v1_video_production_capabilities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project
         * @description 加载视频制作台。
         */
        get: operations["get_project_api_v1_video_projects__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}/assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Asset
         * @description 上传并登记一份真实图片、视频或音频素材。
         */
        post: operations["upload_asset_api_v1_video_projects__project_id__assets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}/episode-commands/{client_request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Project Episode Command */
        get: operations["get_video_project_episode_command_api_v1_video_projects__project_id__episode_commands__client_request_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}/episodes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Video Episodes */
        get: operations["list_video_episodes_api_v1_video_projects__project_id__episodes_get"];
        put?: never;
        /** Create Video Episode */
        post: operations["create_video_episode_api_v1_video_projects__project_id__episodes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}/episodes/reorder": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reorder Video Episodes */
        post: operations["reorder_video_episodes_api_v1_video_projects__project_id__episodes_reorder_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/projects/{project_id}/visual-canons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Visual Canons */
        get: operations["list_visual_canons_api_v1_video_projects__project_id__visual_canons_get"];
        put?: never;
        /** Set Visual Canon Candidate */
        post: operations["set_visual_canon_candidate_api_v1_video_projects__project_id__visual_canons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/visual-canons/{canon_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Visual Canon */
        post: operations["approve_visual_canon_api_v1_video_visual_canons__canon_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Writing Runs */
        get: operations["list_writing_runs_api_v1_writing_runs_get"];
        put?: never;
        /** Start Writing Run */
        post: operations["start_writing_run_api_v1_writing_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Writing Run Status */
        get: operations["get_writing_run_status_api_v1_writing_runs__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs/{task_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Writing Run */
        post: operations["cancel_writing_run_api_v1_writing_runs__task_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs/{task_id}/clarification": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Clarify Writing Run */
        post: operations["clarify_writing_run_api_v1_writing_runs__task_id__clarification_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs/{task_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stream Writing Run Events */
        get: operations["stream_writing_run_events_api_v1_writing_runs__task_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/runs/{task_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume Writing Run */
        post: operations["resume_writing_run_api_v1_writing_runs__task_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Writing Sessions */
        get: operations["list_writing_sessions_api_v1_writing_sessions_get"];
        put?: never;
        /** Create Writing Session */
        post: operations["create_writing_session_api_v1_writing_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Writing Session */
        get: operations["get_writing_session_api_v1_writing_sessions__session_id__get"];
        put?: never;
        post?: never;
        /** Delete Writing Session */
        delete: operations["delete_writing_session_api_v1_writing_sessions__session_id__delete"];
        options?: never;
        head?: never;
        /** Update Writing Session */
        patch: operations["update_writing_session_api_v1_writing_sessions__session_id__patch"];
        trace?: never;
    };
    "/api/v1/writing/sessions/{session_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Writing Message */
        post: operations["add_writing_message_api_v1_writing_sessions__session_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/writing/tasks/{task_id}/artifact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Task Review Artifact */
        get: operations["get_task_review_artifact_api_v1_writing_tasks__task_id__artifact_get"];
        put?: never;
        post?: never;
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
        /** AbsenceSentinel */
        AbsenceSentinel: {
            /** Resourceid */
            resourceId: string;
            /** Resourcetype */
            resourceType: string;
        };
        /** AdoptVideoEpisodeScriptCandidateRequest */
        AdoptVideoEpisodeScriptCandidateRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
        };
        /** AdoptVideoStoryboardCandidateRequest */
        AdoptVideoStoryboardCandidateRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
        };
        /** AppliedStyleSummary */
        AppliedStyleSummary: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** ApplyStyleRequest */
        ApplyStyleRequest: {
            expectedStyleId: string | null;
            styleId: string | null;
        };
        /** ApplyStyleResponse */
        ApplyStyleResponse: {
            /** Effective */
            effective: boolean;
            styleId: string | null;
        };
        /** ApproveVideoEpisodeScriptConfirmationRequest */
        ApproveVideoEpisodeScriptConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Confirmationhash */
            confirmationHash: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
        };
        /** ApproveVideoStoryboardConfirmationRequest */
        ApproveVideoStoryboardConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Confirmationhash */
            confirmationHash: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
        };
        /** ApproveVisualCanonRequest */
        ApproveVisualCanonRequest: {
            /** Candidateassetid */
            candidateAssetId: string;
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
        };
        /** ApprovedBeatPlanSummary */
        ApprovedBeatPlanSummary: {
            /** Scenecount */
            sceneCount: number;
            /** Totalestimatedwords */
            totalEstimatedWords: number;
        };
        /** ArtifactDecisionAcceptedResponse */
        ArtifactDecisionAcceptedResponse: {
            /** Artifactid */
            artifactId: string;
            /** Commandid */
            commandId: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "discard" | "revise";
            /**
             * Deleted
             * @default false
             */
            deleted: boolean;
            /**
             * Engineversion
             * @default 1
             * @constant
             */
            engineVersion: 1;
            /**
             * Savedcount
             * @default 0
             */
            savedCount: number;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /** Taskid */
            taskId: string;
        };
        ArtifactDecisionPublicResponse: components["schemas"]["ArtifactDecisionAcceptedResponse"] | components["schemas"]["WritingRunV2Response"];
        /** ArtifactEvaluationResponse */
        ArtifactEvaluationResponse: {
            /** Artifactid */
            artifactId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Evaluatoragent */
            evaluatorAgent: string;
            /** Id */
            id: string;
            requiredChanges: string | null;
            /** Revision */
            revision: number;
            /** Summary */
            summary: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "pass" | "revise" | "block";
        };
        /** ArtifactSelectionRef */
        ArtifactSelectionRef: {
            index?: number | null;
            /** Section */
            section: string;
        };
        /** BeatPlanDto */
        BeatPlanDto: {
            chapterAcceptanceCriteria: string | null;
            /** Chaptergoal */
            chapterGoal: string;
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            generatedBy: string | null;
            goalId: string | null;
            /** Id */
            id: string;
            mainPlotConnection: string | null;
            /** Scenebeats */
            sceneBeats: components["schemas"]["SceneBeatDto"][];
            status: components["schemas"]["BeatPlanStatus"];
            /** Totalestimatedwords */
            totalEstimatedWords: number;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        BeatPlanStatus: "draft" | "reviewing" | "approved" | "rejected" | "superseded";
        /** BillingSummaryResponse */
        BillingSummaryResponse: {
            /** Balancecredits */
            balanceCredits: string;
            /** Balancemicros */
            balanceMicros: string;
            /** Recentledger */
            recentLedger: components["schemas"]["LedgerEntryResponse"][];
            /** Username */
            username: string;
        };
        /** BillingUsageResponse */
        BillingUsageResponse: {
            monthlyUsage: components["schemas"]["TokenUsageBreakdown"];
            totalUsage: components["schemas"]["TokenUsageBreakdown"];
        };
        /**
         * Format: binary
         * @description 经过归属或供应商令牌校验后流式输出的受控媒体文件
         */
        BinaryFileStream: string;
        /** Body_upload_asset_api_v1_video_projects__project_id__assets_post */
        Body_upload_asset_api_v1_video_projects__project_id__assets_post: {
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "sfx" | "music";
            /**
             * File
             * Format: binary
             */
            file: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "image" | "video" | "audio";
            /** Name */
            name: string;
            /**
             * Sourcekind
             * @default user_upload
             * @enum {string}
             */
            sourceKind: "user_upload" | "authorized_real" | "virtual" | "model_generated";
        };
        /** Body_upload_reference_api_v1_styles__style_id__references_post */
        Body_upload_reference_api_v1_styles__style_id__references_post: {
            /**
             * File
             * Format: binary
             */
            file: string;
        };
        CancelWritingRunPublicResponse: components["schemas"]["CancelWritingRunResponse"] | components["schemas"]["WritingRunV2Response"];
        /** CancelWritingRunRequest */
        CancelWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CancelWritingRunResponse */
        CancelWritingRunResponse: {
            /** Alreadyterminal */
            alreadyTerminal: boolean;
            cancelledCommandId: string | null;
            cancelledJobId: string | null;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /** Effective */
            effective: boolean;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string;
        };
        /** ChapterIdSummary */
        ChapterIdSummary: {
            /** Id */
            id: string;
        };
        /** ChapterListResponse */
        ChapterListResponse: {
            /** Chapters */
            chapters: components["schemas"]["WorkspaceChapter"][];
        };
        /** ChapterMutationResponse */
        ChapterMutationResponse: {
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ChapterProgressDto */
        ChapterProgressDto: {
            /** Chapterid */
            chapterId: string;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ChapterProgressRequest */
        ChapterProgressRequest: {
            /** Content */
            content: string;
            expectedUpdatedAt: string | null;
        };
        /** ChapterRangeScope */
        ChapterRangeScope: {
            /** Chapterendorder */
            chapterEndOrder: number;
            /** Chapterstartorder */
            chapterStartOrder: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "chapter_range";
        };
        /** ChapterScope */
        ChapterScope: {
            /** Chapterid */
            chapterId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "chapter";
        };
        /** @enum {string} */
        ChapterStatus: "drafting" | "review" | "completed";
        /** ChapterStatusRequest */
        ChapterStatusRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            status: components["schemas"]["ChapterStatus"];
        };
        /** ChapterStatusResponse */
        ChapterStatusResponse: {
            completedAt: string | null;
            /** Id */
            id: string;
            status: components["schemas"]["ChapterStatus"];
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ChapterTarget */
        ChapterTarget: {
            /** Id */
            id: string;
            /**
             * Type
             * @constant
             */
            type: "chapter";
        };
        /** CharacterDto */
        CharacterDto: {
            age: string | null;
            aliases: string | null;
            appearance: string | null;
            background: string | null;
            behaviorBoundaries: string | null;
            combatAbility: string | null;
            coreDesire: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            currentStatus: components["schemas"]["CharacterStatus"];
            /** Experiences */
            experiences: components["schemas"]["CharacterExperienceDto"][];
            faction: components["schemas"]["FactionSummary"] | null;
            factionId: string | null;
            gender: string | null;
            /** Id */
            id: string;
            identity: string | null;
            /** Incomingrelations */
            incomingRelations: components["schemas"]["CharacterRelationDto"][];
            /** Name */
            name: string;
            /** Outgoingrelations */
            outgoingRelations: components["schemas"]["CharacterRelationDto"][];
            personality: string | null;
            powerLevel: string | null;
            relationshipPrinciples: string | null;
            shortTermGoal: string | null;
            specialSkills: string | null;
            speechStyle: string | null;
            statusNote: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterExperienceDto */
        CharacterExperienceDto: {
            chapterId: string | null;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Order */
            order: number;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterRelationDto */
        CharacterRelationDto: {
            character?: components["schemas"]["RelationPeer"] | null;
            /** Characterid */
            characterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description: string | null;
            endDate: string | null;
            /** Id */
            id: string;
            /** Intimacy */
            intimacy: number;
            relationType: components["schemas"]["RelationType"];
            startDate: string | null;
            target?: components["schemas"]["RelationPeer"] | null;
            /** Targetid */
            targetId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterResponse */
        CharacterResponse: {
            age?: string | null;
            aliases?: string | null;
            appearance?: string | null;
            background?: string | null;
            behaviorBoundaries?: string | null;
            combatAbility?: string | null;
            coreDesire?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            factionId?: string | null;
            gender?: string | null;
            /** Id */
            id: string;
            identity?: string | null;
            /** Name */
            name: string;
            personality?: string | null;
            powerLevel?: string | null;
            relationshipPrinciples?: string | null;
            shortTermGoal?: string | null;
            specialSkills?: string | null;
            speechStyle?: string | null;
            statusNote?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        CharacterStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
        /** ClarifyWritingRunRequest */
        ClarifyWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Decisionstepid */
            decisionStepId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Usermessage */
            userMessage: string;
        };
        /**
         * ConfirmVideoAssetRequest
         * @description 用户确认素材权利并锁定，受限或拒绝素材不能锁定。
         */
        ConfirmVideoAssetRequest: {
            /**
             * Rightsstatus
             * @enum {string}
             */
            rightsStatus: "confirmed" | "restricted" | "rejected";
        };
        /** ContentDto */
        ContentDto: {
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ContentRequest */
        ContentRequest: {
            content: string | null;
            expectedUpdatedAt: string | null;
        };
        /** ContentResponse */
        ContentResponse: {
            content: string | null;
            createdAt?: string | null;
            /** Id */
            id: string;
            updatedAt?: string | null;
        };
        /** CreateChapterResponse */
        CreateChapterResponse: {
            chapter: components["schemas"]["WorkspaceChapter"];
        };
        /** CreateCharacterRequest */
        CreateCharacterRequest: {
            age?: string | null;
            aliases?: string | null;
            appearance?: string | null;
            background?: string | null;
            behaviorBoundaries?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            combatAbility?: string | null;
            coreDesire?: string | null;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            factionId?: string | null;
            gender?: string | null;
            identity?: string | null;
            /** Name */
            name: string;
            personality?: string | null;
            powerLevel?: string | null;
            relationshipPrinciples?: string | null;
            shortTermGoal?: string | null;
            specialSkills?: string | null;
            speechStyle?: string | null;
            statusNote?: string | null;
        };
        /** CreateCharacterResponse */
        CreateCharacterResponse: {
            age?: string | null;
            aliases?: string | null;
            appearance?: string | null;
            background?: string | null;
            behaviorBoundaries?: string | null;
            combatAbility?: string | null;
            coreDesire?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            /** Effective */
            effective: boolean;
            factionId?: string | null;
            gender?: string | null;
            /** Id */
            id: string;
            identity?: string | null;
            /** Name */
            name: string;
            personality?: string | null;
            powerLevel?: string | null;
            relationshipPrinciples?: string | null;
            shortTermGoal?: string | null;
            specialSkills?: string | null;
            speechStyle?: string | null;
            statusNote?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateExperienceRequest */
        CreateExperienceRequest: {
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Content */
            content: string;
            order?: number | null;
        };
        /** CreateExperienceResponse */
        CreateExperienceResponse: {
            chapterId: string | null;
            /** Characterid */
            characterId: string;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Effective */
            effective: boolean;
            /** Id */
            id: string;
            /** Order */
            order: number;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateFactionRequest */
        CreateFactionRequest: {
            aliases?: string | null;
            baseId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            description?: string | null;
            /** Name */
            name: string;
            type?: string | null;
        };
        /** CreateFactionResponse */
        CreateFactionResponse: {
            aliases?: string | null;
            baseId?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            /** Effective */
            effective: boolean;
            /** Id */
            id: string;
            /** Name */
            name: string;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateForeshadowingRequest */
        CreateForeshadowingRequest: {
            expectedPayoff?: string | null;
            /** Name */
            name: string;
            payoffAt?: string | null;
            plantedAt?: string | null;
            plantedContent?: string | null;
            /**
             * Status
             * @default active
             * @enum {string}
             */
            status: "active" | "paid_off" | "abandoned";
        };
        /** CreateGlossaryRequest */
        CreateGlossaryRequest: {
            category?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Definition */
            definition: string;
            /** Term */
            term: string;
        };
        /** CreateGlossaryResponse */
        CreateGlossaryResponse: {
            category?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Definition */
            definition: string;
            /** Effective */
            effective: boolean;
            /** Id */
            id: string;
            /** Term */
            term: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateItemRequest */
        CreateItemRequest: {
            aliases?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            description?: string | null;
            effect?: string | null;
            /** Name */
            name: string;
            origin?: string | null;
            ownerId?: string | null;
            rarity?: string | null;
            type?: string | null;
        };
        /** CreateItemResponse */
        CreateItemResponse: {
            aliases?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            effect?: string | null;
            /** Effective */
            effective: boolean;
            /** Id */
            id: string;
            /** Name */
            name: string;
            origin?: string | null;
            ownerId?: string | null;
            rarity?: string | null;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateLocationRequest */
        CreateLocationRequest: {
            aliases?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            climate?: string | null;
            culture?: string | null;
            description?: string | null;
            /** Name */
            name: string;
            parentId?: string | null;
            type?: string | null;
        };
        /** CreateLocationResponse */
        CreateLocationResponse: {
            aliases?: string | null;
            climate?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            culture?: string | null;
            description?: string | null;
            /** Effective */
            effective: boolean;
            /** Id */
            id: string;
            /** Name */
            name: string;
            parentId?: string | null;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateMessageRequest */
        CreateMessageRequest: {
            agentId?: string | null;
            /** Content */
            content: string;
            intent?: string | null;
            metadata?: components["schemas"]["JsonValue"] | null;
            parentId?: string | null;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "agent" | "system";
        };
        /** CreateNovelRequest */
        CreateNovelRequest: {
            clientRequestId?: string | null;
            coreSellingPoint?: string | null;
            firstChapterGoal?: string | null;
            genre?: string | null;
            /** Name */
            name: string;
            protagonist?: string | null;
            readerPromise?: string | null;
            sourceKind?: components["schemas"]["ShortMediumSourceKind"] | null;
            sourceText?: string | null;
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            summary?: string | null;
            targetTotalWordCount?: number | null;
        };
        /** CreateNovelResponse */
        CreateNovelResponse: {
            /** Chapterid */
            chapterId: string;
            /** Novelid */
            novelId: string;
        };
        /** CreateOutlineNodeRequest */
        CreateOutlineNodeRequest: {
            actualWordCount?: number | null;
            chapterEndOrder?: number | null;
            chapterStartOrder?: number | null;
            /** Clientrequestid */
            clientRequestId: string;
            content?: string | null;
            estimatedWordCount?: number | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            linkedChapterId?: string | null;
            /**
             * Order
             * @default 0
             */
            order: number;
            parentId?: string | null;
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /** Title */
            title: string;
        };
        /** CreatePhoneChallengeRequest */
        CreatePhoneChallengeRequest: {
            /**
             * Acceptedterms
             * @constant
             */
            acceptedTerms: true;
            /** Captchaverifyparam */
            captchaVerifyParam: string;
            /** Clientrequestid */
            clientRequestId: string;
            /** Consentversion */
            consentVersion: string;
            /** Phone */
            phone: string;
        };
        /** CreateReferenceRequest */
        CreateReferenceRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Content */
            content: string;
            sourceUrl?: string | null;
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
        };
        /** CreateReferenceResponse */
        CreateReferenceResponse: {
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            createdAt?: string | null;
            /** Effective */
            effective: boolean;
            errorMessage: string | null;
            /** Id */
            id: string;
            /**
             * Ragstatus
             * @enum {string}
             */
            ragStatus: "disabled" | "ready" | "failed";
            sourceUrl?: string | null;
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
            updatedAt?: string | null;
        };
        /** CreateRelationRequest */
        CreateRelationRequest: {
            /** Characterid */
            characterId: string;
            /** Clientrequestid */
            clientRequestId: string;
            description?: string | null;
            endDate?: string | null;
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            startDate?: string | null;
            /** Targetid */
            targetId: string;
        };
        /** CreateRelationResponse */
        CreateRelationResponse: {
            /** Characterid */
            characterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            /** Effective */
            effective: boolean;
            endDate?: string | null;
            /** Id */
            id: string;
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            startDate?: string | null;
            /** Targetid */
            targetId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CreateStyleRequest */
        CreateStyleRequest: {
            /** Name */
            name: string;
        };
        /** CreateVideoEpisodeEditVersionRequest */
        CreateVideoEpisodeEditVersionRequest: {
            basedOnVersionId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Clips */
            clips: components["schemas"]["VideoEpisodeEditClipInput"][];
            /** Expectedheadrevision */
            expectedHeadRevision: number;
            /** Omissions */
            omissions?: components["schemas"]["VideoEpisodeShotOmissionInput"][];
        };
        /** CreateVideoEpisodeMixVersionRequest */
        CreateVideoEpisodeMixVersionRequest: {
            /** Audioclips */
            audioClips?: components["schemas"]["VideoEpisodeAudioClipInput"][];
            basedOnVersionId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Editversionid */
            editVersionId: string;
            /** Expectedheadrevision */
            expectedHeadRevision: number;
            /** Subtitlecues */
            subtitleCues?: components["schemas"]["VideoEpisodeSubtitleCueInput"][];
        };
        /** CreateVideoEpisodeRequest */
        CreateVideoEpisodeRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Creativeintent
             * @default
             */
            creativeIntent: string;
            targetDurationSeconds?: number | null;
            /** Title */
            title: string;
        };
        /** CreateVideoEpisodeSourceSetRequest */
        CreateVideoEpisodeSourceSetRequest: {
            basedOnVersionId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Sources */
            sources: components["schemas"]["VideoEpisodeSourceSelection"][];
        };
        /** CreateVideoProductionBaselineRequest */
        CreateVideoProductionBaselineRequest: {
            basedOnBaselineId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
            /** Expectedproductionrevision */
            expectedProductionRevision: number;
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeInput"][];
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotadoptions */
            shotAdoptions?: components["schemas"]["VideoProductionBaselineAdoptionInput"][];
            /** Storyboardversionid */
            storyboardVersionId: string;
        };
        /**
         * CreateVideoProjectRequest
         * @description 创建一个独立于写作任务的视频项目。
         */
        CreateVideoProjectRequest: {
            /**
             * Mode
             * @default highlight
             * @enum {string}
             */
            mode: "concept" | "trailer" | "highlight" | "series";
            /**
             * Targetaspectratio
             * @default 16:9
             * @enum {string}
             */
            targetAspectRatio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /**
             * Targetlanguage
             * @default zh-CN
             */
            targetLanguage: string;
            /** Title */
            title: string;
        };
        /** CreateVideoTakeAdoptionRequest */
        CreateVideoTakeAdoptionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            comparison: components["schemas"]["VideoTakeAdoptionComparison"];
            /** Expectedproductionrevision */
            expectedProductionRevision: number;
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Sourcetakeid */
            sourceTakeId: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
        };
        /**
         * CreateVisualCanonCandidateRequest
         * @description 把已上传且已确认权利的图片放入一个视觉设定槽的候选位置。
         */
        CreateVisualCanonCandidateRequest: {
            /** Candidateassetid */
            candidateAssetId: string;
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Defaultstrength
             * @default 70
             */
            defaultStrength: number;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Excludefeatures */
            excludeFeatures?: string[];
            /** Expectedrevision */
            expectedRevision: number;
            /** Includefeatures */
            includeFeatures?: string[];
            /** Label */
            label: string;
            /** Settingid */
            settingId: string;
            /**
             * Settingkind
             * @enum {string}
             */
            settingKind: "character" | "location" | "item";
            /** Variantkey */
            variantKey: string;
        };
        /** CreateWritingSessionRequest */
        CreateWritingSessionRequest: {
            /** Chapterid */
            chapterId: string;
            /** Novelid */
            novelId: string;
            title?: string | null;
        };
        /** DashboardNovel */
        DashboardNovel: {
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
            /** Chapters */
            chapters: components["schemas"]["ChapterIdSummary"][];
            /** Id */
            id: string;
            /** Name */
            name: string;
            summary: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** DashboardResponse */
        DashboardResponse: {
            /** Novels */
            novels: components["schemas"]["DashboardNovel"][];
        };
        /** DecideVideoImpactReviewRequest */
        DecideVideoImpactReviewRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Decisions */
            decisions: components["schemas"]["VideoImpactDecision"][];
            /** Expectedrevision */
            expectedRevision: number;
        };
        /** DeleteEntityRequest */
        DeleteEntityRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** DeleteImpactResponse */
        DeleteImpactResponse: {
            /** Affected */
            affected: {
                [key: string]: number;
            };
            /** Deletedid */
            deletedId: string;
            /**
             * Deletedtype
             * @enum {string}
             */
            deletedType: "characters" | "items" | "locations" | "factions" | "glossary" | "experience" | "relation";
        };
        /** DeleteOutlineNodeRequest */
        DeleteOutlineNodeRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** DeleteOutlineNodeResponse */
        DeleteOutlineNodeResponse: {
            /** Deletedid */
            deletedId: string;
            /** Effective */
            effective: boolean;
        };
        /** DeleteReferenceAffected */
        DeleteReferenceAffected: {
            /** Ragchunks */
            ragChunks: number;
            /**
             * Ragdocuments
             * @enum {integer}
             */
            ragDocuments: 0 | 1;
            /**
             * Reference
             * @constant
             */
            reference: 1;
        };
        /** DeleteReferenceImpactResponse */
        DeleteReferenceImpactResponse: {
            affected: components["schemas"]["DeleteReferenceAffected"];
            /** Deletedid */
            deletedId: string;
            /**
             * Deletedtype
             * @constant
             */
            deletedType: "reference";
        };
        /** DeleteReferenceRequest */
        DeleteReferenceRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** DiffBlock */
        DiffBlock: {
            /** Newend */
            newEnd: number;
            /** Newstart */
            newStart: number;
            newText?: string | null;
            /** Oldend */
            oldEnd: number;
            /** Oldstart */
            oldStart: number;
            oldText?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "insert" | "delete" | "replace";
        };
        /** @enum {string} */
        DocumentType: "outline" | "manuscript";
        /** DocumentVersionPayload */
        DocumentVersionPayload: {
            baseVersionId?: string | null;
            clientRequestId?: string | null;
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdfromselection
             * @default false
             */
            createdFromSelection: boolean;
            documentType: components["schemas"]["DocumentType"];
            /**
             * Kind
             * @enum {string}
             */
            kind: "outline_draft" | "chapter_draft";
            restoredFromVersionId?: string | null;
            selectedTextHash?: string | null;
            selectionEnd?: number | null;
            selectionStart?: number | null;
            source: components["schemas"]["VersionSource"];
            sourceJobId?: string | null;
            sourceKind?: ("idea" | "opening" | "ending" | "outline" | "mixed") | null;
            sourceOutlineVersionId?: string | null;
            sourceTaskId?: string | null;
            sourceText?: string | null;
            userInstruction?: string | null;
            /** Versionnumber */
            versionNumber: number;
        };
        /** ErrorResponse */
        ErrorResponse: {
            /** Code */
            code: string;
            details: components["schemas"]["JsonValue"] | null;
            /** Message */
            message: string;
            /** Requestid */
            requestId: string;
        };
        /** ExperienceResponse */
        ExperienceResponse: {
            chapterId: string | null;
            /** Characterid */
            characterId: string;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Order */
            order: number;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FactionDto */
        FactionDto: {
            aliases: string | null;
            baseId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            type: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FactionResponse */
        FactionResponse: {
            aliases?: string | null;
            baseId?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FactionSummary */
        FactionSummary: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** ForeshadowingResponse */
        ForeshadowingResponse: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            expectedPayoff?: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            payoffAt?: string | null;
            plantedAt?: string | null;
            plantedContent?: string | null;
            /**
             * Status
             * @default active
             * @enum {string}
             */
            status: "active" | "paid_off" | "abandoned";
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** GlossaryDto */
        GlossaryDto: {
            category: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Definition */
            definition: string;
            /** Id */
            id: string;
            /** Term */
            term: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** GlossaryResponse */
        GlossaryResponse: {
            category?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Definition */
            definition: string;
            /** Id */
            id: string;
            /** Term */
            term: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ItemDto */
        ItemDto: {
            aliases: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description: string | null;
            effect: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            origin: string | null;
            owner: components["schemas"]["OwnerSummary"] | null;
            ownerId: string | null;
            rarity: string | null;
            type: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ItemResponse */
        ItemResponse: {
            aliases?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            effect?: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            origin?: string | null;
            ownerId?: string | null;
            rarity?: string | null;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        JsonValue: unknown;
        /** LastMessageResponse */
        LastMessageResponse: {
            agentId: string | null;
            /** Content */
            content: string;
            /** Role */
            role: string;
        };
        /** LedgerEntryResponse */
        LedgerEntryResponse: {
            /** Amountmicros */
            amountMicros: string;
            /** Balanceaftermicros */
            balanceAfterMicros: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            note: string | null;
            /** Type */
            type: string;
        };
        /** LiveHealthResponse */
        LiveHealthResponse: {
            /**
             * Service
             * @constant
             */
            service: "core-api";
            /**
             * Status
             * @constant
             */
            status: "ok";
        };
        /** LocationDto */
        LocationDto: {
            aliases: string | null;
            climate: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            culture: string | null;
            description: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            parentId: string | null;
            type: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** LocationResponse */
        LocationResponse: {
            aliases?: string | null;
            climate?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            culture?: string | null;
            description?: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            parentId?: string | null;
            type?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /**
             * Password
             * Format: password
             */
            password: string;
            /** Username */
            username: string;
        };
        /** LongSerialStartWritingRunRequest */
        LongSerialStartWritingRunRequest: {
            /** Chapterid */
            chapterId: string;
            /** Clientrequestid */
            clientRequestId: string;
            /** Novelid */
            novelId: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "answer_question" | "create_lore" | "revise_lore" | "create_outline" | "revise_outline" | "plan_chapter" | "write_chapter" | "rewrite_scene" | "rewrite_chapter_selection" | "rewrite_outline_selection" | "review_chapter" | "manage_foreshadowing";
            /** Scope */
            scope: components["schemas"]["ChapterScope"] | components["schemas"]["ChapterRangeScope"] | components["schemas"]["OutlineNodeScope"] | components["schemas"]["NovelScope"];
            selectionAttachmentMetadata?: components["schemas"]["SelectionAttachmentMetadata"] | null;
            selectionTarget?: components["schemas"]["SelectionTarget"] | null;
            target: components["schemas"]["ChapterTarget"];
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
            /** Userinstruction */
            userInstruction: string;
            /**
             * Workflow
             * @constant
             */
            workflow: "long_serial";
            writingSessionId?: string | null;
        };
        /** ManualVersionRequest */
        ManualVersionRequest: {
            baseVersionId?: string | null;
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Confirmationhash */
            confirmationHash: string;
            /** Contenthash */
            contentHash: string;
            documentType: components["schemas"]["DocumentType"];
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            summary?: string | null;
        };
        /** MessageResponse */
        MessageResponse: {
            agentId: string | null;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            intent: string | null;
            metadata: components["schemas"]["JsonValue"] | null;
            parentId: string | null;
            /** Role */
            role: string;
            /** Sessionid */
            sessionId: string;
        };
        /**
         * ModelProfileRef
         * @description Core 授权的逻辑模型 Profile；不包含 Agent 部署配置。
         */
        ModelProfileRef: {
            /** Deploymentprofilekey */
            deploymentProfileKey: string;
            /** Profile */
            profile: string;
            promptProfile: components["schemas"]["PromptProfileRef"];
            /**
             * Reasoningmode
             * @enum {string}
             */
            reasoningMode: "disabled" | "bounded";
            /** Version */
            version: number;
        };
        /** NaturalStartWritingRunRequest */
        NaturalStartWritingRunRequest: {
            /** Chapterid */
            chapterId: string;
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Inputmode
             * @constant
             */
            inputMode: "natural";
            /** Novelid */
            novelId: string;
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
            /** Userinstruction */
            userInstruction: string;
            /**
             * Workflow
             * @constant
             */
            workflow: "long_serial";
            /** Writingsessionid */
            writingSessionId: string;
        };
        /** NovelResponse */
        NovelResponse: {
            appliedStyleId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            storyLengthProfile?: components["schemas"]["StoryLengthProfile"] | null;
            storyProgress: string | null;
            summary: string | null;
            targetTotalWordCount?: number | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** NovelScope */
        NovelScope: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "novel";
        };
        /** OutlineContentRequest */
        OutlineContentRequest: {
            /** Content */
            content: string;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** OutlineContentResponse */
        OutlineContentResponse: {
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** OutlineNodeDto */
        OutlineNodeDto: {
            actualWordCount: number | null;
            chapterEndOrder: number | null;
            chapterStartOrder: number | null;
            content: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            estimatedWordCount: number | null;
            /** Id */
            id: string;
            kind: components["schemas"]["OutlineNodeKind"];
            linkedChapterId: string | null;
            /** Order */
            order: number;
            parentId: string | null;
            status: components["schemas"]["OutlineNodeStatus"];
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        OutlineNodeKind: "stage" | "plot_unit" | "chapter_group";
        /** OutlineNodeMutationResponse */
        OutlineNodeMutationResponse: {
            actualWordCount?: number | null;
            chapterEndOrder?: number | null;
            chapterStartOrder?: number | null;
            content?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Effective */
            effective: boolean;
            estimatedWordCount?: number | null;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            linkedChapterId?: string | null;
            /**
             * Order
             * @default 0
             */
            order: number;
            parentId?: string | null;
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** OutlineNodeResponse */
        OutlineNodeResponse: {
            actualWordCount?: number | null;
            chapterEndOrder?: number | null;
            chapterStartOrder?: number | null;
            content?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            estimatedWordCount?: number | null;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            linkedChapterId?: string | null;
            /**
             * Order
             * @default 0
             */
            order: number;
            parentId?: string | null;
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** OutlineNodeScope */
        OutlineNodeScope: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "outline_node";
            /** Outlinenodeid */
            outlineNodeId: string;
        };
        /** @enum {string} */
        OutlineNodeStatus: "planned" | "in_progress" | "completed" | "skipped";
        /** OwnerSummary */
        OwnerSummary: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** PhoneChallengeResponse */
        PhoneChallengeResponse: {
            /** Challengeid */
            challengeId: string;
            /** Expiresinseconds */
            expiresInSeconds: number;
            /** Resendafterseconds */
            resendAfterSeconds: number;
        };
        /** PhoneLoginResponse */
        PhoneLoginResponse: {
            /** Creditbalancemicros */
            creditBalanceMicros: string;
            /** Id */
            id: string;
            /** Isnewuser */
            isNewUser: boolean;
            /** Maskedphone */
            maskedPhone: string;
            /** Username */
            username: string;
        };
        /** PlotProgressDto */
        PlotProgressDto: {
            currentConflict: string | null;
            currentGoal: string | null;
            /** Currentstage */
            currentStage: string;
            /** Id */
            id: string;
            nextMilestone: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** PlotProgressRequest */
        PlotProgressRequest: {
            currentConflict?: string | null;
            currentGoal?: string | null;
            /** Currentstage */
            currentStage: string;
            expectedUpdatedAt: string | null;
            nextMilestone?: string | null;
        };
        /** PlotProgressResponse */
        PlotProgressResponse: {
            currentConflict?: string | null;
            currentGoal?: string | null;
            /** Currentstage */
            currentStage: string;
            /** Id */
            id: string;
            nextMilestone?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** PortraitAcceptedResponse */
        PortraitAcceptedResponse: {
            /**
             * Status
             * @constant
             */
            status: "pending";
            /** Taskid */
            taskId: string;
        };
        /** PortraitTaskResponse */
        PortraitTaskResponse: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            errorMessage: string | null;
            /** Id */
            id: string;
            section: ("creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits") | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "processing" | "success" | "error";
            /** Styleid */
            styleId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** PrepareVideoEpisodeScriptConfirmationRequest */
        PrepareVideoEpisodeScriptConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
        };
        /** PrepareVideoStoryboardConfirmationRequest */
        PrepareVideoStoryboardConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
        };
        /**
         * PromptProfileRef
         * @description Manifest 管理的静态 system prompt 身份；正文由双端 Registry 按哈希校验。
         */
        PromptProfileRef: {
            /** Name */
            name: string;
            /** Sha256 */
            sha256: string;
            /** Version */
            version: number;
        };
        /** QualityCheckDto */
        QualityCheckDto: {
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            qualityGate: components["schemas"]["QualityGate"] | null;
            result: string | null;
            rewriteBrief: string | null;
            scoreEndingHook: number | null;
            scoreHook: number | null;
            scoreOverall: number | null;
            scorePacing: number | null;
            scorePayoff: number | null;
            scoreReaderPromise: number | null;
            scoreTension: number | null;
            status: components["schemas"]["QualityCheckStatus"];
            summary: string | null;
            /** Title */
            title: string;
            type: components["schemas"]["QualityCheckType"];
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        QualityCheckStatus: "pending" | "running" | "completed" | "skipped" | "failed";
        /** @enum {string} */
        QualityCheckType: "consistency" | "lore_sync" | "editorial" | "craft";
        /** @enum {string} */
        QualityGate: "pass" | "revise" | "rewrite";
        /** @enum {string} */
        RagDocumentStatus: "disabled" | "ready" | "failed";
        /** RagSearchRequest */
        RagSearchRequest: {
            /** Queryembedding */
            queryEmbedding: number[];
            /**
             * Topk
             * @default 5
             */
            topK: number;
        };
        /** RagSearchResult */
        RagSearchResult: {
            /** Chunkindex */
            chunkIndex: number;
            /** Score */
            score: number;
            /** Sourceid */
            sourceId: string;
            /** Text */
            text: string;
            /** Title */
            title: string;
        };
        /** ReadyHealthResponse */
        ReadyHealthResponse: {
            backgroundTasks?: {
                [key: string]: string;
            } | null;
            /** Checks */
            checks: {
                [key: string]: "ok" | "failed";
            };
            /**
             * Service
             * @constant
             */
            service: "core-api";
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "not_ready";
        };
        /** ReferenceDto */
        ReferenceDto: {
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            errorMessage: string | null;
            /** Id */
            id: string;
            ragStatus: components["schemas"]["RagDocumentStatus"];
            sourceUrl: string | null;
            /** Title */
            title: string;
            type: components["schemas"]["ReferenceType"];
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ReferenceMaterialResponse */
        ReferenceMaterialResponse: {
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            createdAt?: string | null;
            errorMessage: string | null;
            /** Id */
            id: string;
            /**
             * Ragstatus
             * @enum {string}
             */
            ragStatus: "disabled" | "ready" | "failed";
            sourceUrl?: string | null;
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
            updatedAt?: string | null;
        };
        /** @enum {string} */
        ReferenceType: "note" | "web" | "book" | "image" | "custom";
        /** RegisterRequest */
        RegisterRequest: {
            /**
             * Confirmpassword
             * Format: password
             */
            confirmPassword: string;
            /**
             * Password
             * Format: password
             */
            password: string;
            /** Username */
            username: string;
        };
        /** ReindexAcceptedResponse */
        ReindexAcceptedResponse: {
            /**
             * Accepted
             * @constant
             */
            accepted: true;
        };
        /** ReindexReferenceRequest */
        ReindexReferenceRequest: {
            /** Expectedcontenthash */
            expectedContentHash: string;
        };
        /** RelationPeer */
        RelationPeer: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** RelationResponse */
        RelationResponse: {
            /** Characterid */
            characterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            description?: string | null;
            endDate?: string | null;
            /** Id */
            id: string;
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            startDate?: string | null;
            /** Targetid */
            targetId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        RelationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
        /** ReorderVideoEpisodesRequest */
        ReorderVideoEpisodesRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Episodeids */
            episodeIds: string[];
            /** Expectedprojectrevision */
            expectedProjectRevision: number;
        };
        /**
         * ResolvedModelRef
         * @description Agent 对逻辑 Profile 的一次可审计部署解析。
         */
        ResolvedModelRef: {
            /** Capabilityversion */
            capabilityVersion: string;
            /** Deploymentfingerprint */
            deploymentFingerprint: string;
            /** Deploymentprofilekey */
            deploymentProfileKey: string;
            /** Endpointprofile */
            endpointProfile: string;
            /** Model */
            model: string;
            /** Provider */
            provider: string;
            /**
             * Reasoningmode
             * @enum {string}
             */
            reasoningMode: "disabled" | "bounded";
            /**
             * Structuredoutputroute
             * @enum {string}
             */
            structuredOutputRoute: "responses_json_schema_v1" | "chat_json_output_v1" | "quality_strict_tool_v1" | "plain_text_v1" | "embeddings_v1";
            /**
             * Supportsrequestidempotency
             * @description 仅当 Provider 确实原样传递 ExecutionStepRequest.idempotencyKey 时为 true
             */
            supportsRequestIdempotency: boolean;
            /** Transportprofile */
            transportProfile: string;
        } & ({
            model?: unknown;
            /** @constant */
            structuredOutputRoute?: "embeddings_v1";
        } | {
            model?: unknown;
            /** @enum {unknown} */
            structuredOutputRoute?: "responses_json_schema_v1" | "chat_json_output_v1" | "quality_strict_tool_v1" | "plain_text_v1";
        });
        /** ResumeWritingRunRequest */
        ResumeWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            userMessage?: string | null;
            writingSessionId?: string | null;
        };
        /** ResumeWritingRunResponse */
        ResumeWritingRunResponse: {
            /**
             * Accepted
             * @constant
             */
            accepted: true;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string;
        };
        /** RetryVideoEpisodeExportRequest */
        RetryVideoEpisodeExportRequest: {
            /** Clientrequestid */
            clientRequestId: string;
        };
        /**
         * RetryVideoEpisodeShotRenderRequest
         * @description 精确复制旧任务冻结输入；不能借重试读取新的制作基线。
         */
        RetryVideoEpisodeShotRenderRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Feeconfirmed
             * @default false
             */
            feeConfirmed: boolean;
        };
        /** ReviewArtifactDecisionRequest */
        ReviewArtifactDecisionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "discard" | "revise";
            editedContent?: string | null;
            editedReplacement?: string | null;
            /**
             * Engineversion
             * @description 审核决定引擎版本；省略只兼容解释为 V1，V2 必须显式提交 2
             * @default 1
             * @enum {integer}
             */
            engineVersion: 1 | 2;
            /**
             * Expectedrevision
             * @description V1 为既有草案修订号；V2 为规范 expectedArtifactRevision wire 字段
             */
            expectedRevision: number;
            selectedUpdateRefs?: components["schemas"]["ArtifactSelectionRef"][] | null;
            userMessage?: string | null;
        };
        /** ReviewArtifactListResponse */
        ReviewArtifactListResponse: {
            /** Items */
            items: components["schemas"]["ReviewArtifactResponse"][];
            nextCursor: string | null;
        };
        /** ReviewArtifactResponse */
        ReviewArtifactResponse: {
            artifactKey: string | null;
            chapterId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            createdByAgent: string | null;
            diff: components["schemas"]["JsonValue"] | null;
            /**
             * Engineversion
             * @enum {integer}
             */
            engineVersion: 1 | 2;
            /** Evaluations */
            evaluations?: components["schemas"]["ArtifactEvaluationResponse"][];
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent_updates" | "outline_draft" | "chapter_draft" | "lore_draft" | "revision_brief" | "beat_plan_draft" | "chapter_content" | "beat_plan" | "freeform_markdown";
            /** Novelid */
            novelId: string;
            /** Payload */
            payload: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            reviewerAgent: string | null;
            /** Revision */
            revision: number;
            /**
             * Sourcebindingstatus
             * @enum {string}
             */
            sourceBindingStatus: "verified" | "legacy_missing" | "not_yet_supported";
            sourceBindings: components["schemas"]["SourceBinding"][] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "under_review" | "awaiting_user" | "applying" | "applied";
            summary: string | null;
            taskId: string | null;
            title: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            updatedByAgent: string | null;
            workflowRunId: string | null;
        };
        /** ReviewArtifactSummaryListResponse */
        ReviewArtifactSummaryListResponse: {
            /** Items */
            items: components["schemas"]["ReviewArtifactSummaryResponse"][];
            nextCursor: string | null;
        };
        /**
         * ReviewArtifactSummaryResponse
         * @description 集合查询使用的有界索引；完整内容必须按精确 revision 单独读取。
         */
        ReviewArtifactSummaryResponse: {
            /** Actionable */
            actionable: boolean;
            artifactKey: string | null;
            chapterId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Engineversion
             * @enum {integer}
             */
            engineVersion: 1 | 2;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent_updates" | "outline_draft" | "chapter_draft" | "lore_draft" | "revision_brief" | "beat_plan_draft" | "chapter_content" | "beat_plan" | "freeform_markdown";
            /** Novelid */
            novelId: string;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "under_review" | "awaiting_user" | "applying" | "applied";
            summary: string | null;
            taskId: string | null;
            title: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            workflowRunId: string | null;
        };
        /** RunQualityCheckRequest */
        RunQualityCheckRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            message?: string | null;
            taskId?: string | null;
        };
        /** RunQualityCheckResponse */
        RunQualityCheckResponse: {
            /** Accepted */
            accepted: boolean;
            /** Checkid */
            checkId: string;
            /** Taskid */
            taskId: string;
        };
        /** SaveVideoEpisodeScriptDraftRequest */
        SaveVideoEpisodeScriptDraftRequest: {
            baseScriptVersionId: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Expectedrevision */
            expectedRevision: number;
            sourceSetVersionId: string | null;
        };
        /** SaveVideoStoryboardDraftRequest */
        SaveVideoStoryboardDraftRequest: {
            baseStoryboardVersionId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Expectedrevision */
            expectedRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
        };
        /** SceneBeatDto */
        SceneBeatDto: {
            /** Acceptancecriteria */
            acceptanceCriteria: string;
            /** Characters */
            characters: string;
            conflict: string | null;
            /** Estimatedwords */
            estimatedWords: number;
            foreshadowingRefs: string | null;
            /** Goal */
            goal: string;
            /** Id */
            id: string;
            /** Order */
            order: number;
        };
        /**
         * SelectionAttachmentMetadata
         * @description 选区来源快照的 UI 元数据；不包含也不承载权威正文。
         */
        SelectionAttachmentMetadata: {
            /** Basecontenthash */
            baseContentHash: string;
            /**
             * Baseupdatedat
             * Format: date-time
             */
            baseUpdatedAt: string;
            /** Resourceid */
            resourceId: string;
            /**
             * Resourcetype
             * @enum {string}
             */
            resourceType: "chapter_content" | "outline_content" | "outline_node_content";
            /** Selectedtexthash */
            selectedTextHash: string;
            /** Selectionend */
            selectionEnd: number;
            /** Selectionpreview */
            selectionPreview: string;
            /** Selectionstart */
            selectionStart: number;
            /** Sourcelabel */
            sourceLabel: string;
        };
        /**
         * SelectionTarget
         * @description 客户端提交的不可变选区身份；正文由 Core 从权威源派生。
         */
        SelectionTarget: {
            /** Basecontenthash */
            baseContentHash: string;
            /**
             * Baseupdatedat
             * Format: date-time
             */
            baseUpdatedAt: string;
            /** Resourceid */
            resourceId: string;
            /**
             * Resourcetype
             * @enum {string}
             */
            resourceType: "chapter_content" | "outline_content" | "outline_node_content";
            /** Selectedtexthash */
            selectedTextHash: string;
            /** Selectionend */
            selectionEnd: number;
            /** Selectionstart */
            selectionStart: number;
        };
        /** @enum {string} */
        ShortMediumSourceKind: "idea" | "opening" | "ending" | "outline" | "mixed";
        /** ShortMediumStartWritingRunRequest */
        ShortMediumStartWritingRunRequest: {
            baseVersionId?: string | null;
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Documenttype
             * @enum {string}
             */
            documentType: "outline" | "manuscript";
            /** Novelid */
            novelId: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "generate_outline" | "generate_manuscript" | "replace_selection" | "full_check";
            selectedTextHash?: string | null;
            selectionEnd?: number | null;
            selectionStart?: number | null;
            sourceOutlineVersionId?: string | null;
            userInstruction?: string | null;
            /**
             * Workflow
             * @constant
             */
            workflow: "short_medium";
        };
        /** SourceBinding */
        SourceBinding: {
            absenceSentinel: components["schemas"]["AbsenceSentinel"] | null;
            contentSha256: string | null;
            /** Exists */
            exists: boolean;
            /** Resourceid */
            resourceId: string;
            /** Resourcetype */
            resourceType: string;
            revision: number | null;
            updatedAt: string | null;
        };
        /** StartVideoEpisodeExportRequest */
        StartVideoEpisodeExportRequest: {
            /**
             * Burnsubtitles
             * @default true
             */
            burnSubtitles: boolean;
            /** Clientrequestid */
            clientRequestId: string;
            /** Editversionid */
            editVersionId: string;
            /**
             * Framespersecond
             * @default 24
             * @enum {integer}
             */
            framesPerSecond: 24 | 25 | 30;
            /** Mixversionid */
            mixVersionId: string;
            /**
             * Resolution
             * @default 720p
             * @enum {string}
             */
            resolution: "720p" | "1080p";
        };
        /** StartVideoEpisodeScriptRunRequest */
        StartVideoEpisodeScriptRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Instruction */
            instruction: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "episode_script_generate" | "episode_script_revise";
            /** Selectedsceneids */
            selectedSceneIds?: string[];
        };
        /**
         * StartVideoEpisodeShotRenderRequest
         * @description 生成参数来自制作基线；请求只能确认本次业务身份与费用事实。
         */
        StartVideoEpisodeShotRenderRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Feeconfirmed
             * @default false
             */
            feeConfirmed: boolean;
        };
        /** StartVideoStoryboardRunRequest */
        StartVideoStoryboardRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Instruction */
            instruction: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "episode_storyboard_generate" | "episode_storyboard_revise";
            /** Scriptversionid */
            scriptVersionId: string;
            /** Selectedshotids */
            selectedShotIds?: string[];
        };
        /** StartWritingRunRequest */
        StartWritingRunRequest: {
            /** Chapterid */
            chapterId: string;
            /** Clientrequestid */
            clientRequestId: string;
            /** Novelid */
            novelId: string;
            /** Selectedagents */
            selectedAgents?: ("设定" | "剧情" | "写作" | "校验" | "编辑")[];
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
            /** Usermessage */
            userMessage: string;
            writingSessionId?: string | null;
        };
        /** @enum {string} */
        StoryLengthProfile: "short_medium" | "long_serial";
        /** StyleReferenceResponse */
        StyleReferenceResponse: {
            /** Charcount */
            charCount: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            errorMessage: string | null;
            /** Filename */
            filename: string;
            /** Id */
            id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "error";
            /** Styleid */
            styleId: string;
        };
        /** StyleResponse */
        StyleResponse: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            creativeMethodology: string | null;
            errorMessage: string | null;
            expressionFeatures: string | null;
            generationStyle: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Originalcharcount */
            originalCharCount: number;
            portraitMarkdown: string | null;
            /** References */
            references: components["schemas"]["StyleReferenceResponse"][];
            /**
             * Sourcetype
             * @enum {string}
             */
            sourceType: "manual" | "agent";
            styleTraits: string | null;
            /** Tasks */
            tasks: components["schemas"]["PortraitTaskResponse"][];
            /** Truncated */
            truncated: boolean;
            uniqueMarkers: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Usedcharcount */
            usedCharCount: number;
        };
        /** @enum {string} */
        StyleSourceType: "manual" | "agent";
        /** StyleSummary */
        StyleSummary: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            portraitMarkdown?: string | null;
            sourceType: components["schemas"]["StyleSourceType"];
        };
        /** TaskModelUsageCall */
        TaskModelUsageCall: {
            agentId: string | null;
            /** Cachedtokens */
            cachedTokens: number;
            /** Completiontokens */
            completionTokens: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Model */
            model: string;
            promptCacheMissTokens: number | null;
            /** Prompttokens */
            promptTokens: number;
            reasoningTokens: number | null;
            /** Requestid */
            requestId: string;
            /** Runid */
            runId: string;
            /** Tokendetailscomplete */
            tokenDetailsComplete: boolean;
            /** Totaltokens */
            totalTokens: number;
            visibleCompletionTokens: number | null;
        };
        /** TaskModelUsageResponse */
        TaskModelUsageResponse: {
            /** Cachedtokens */
            cachedTokens: number;
            /** Calls */
            calls: components["schemas"]["TaskModelUsageCall"][];
            /** Completiontokens */
            completionTokens: number;
            promptCacheMissTokens: number | null;
            /** Prompttokens */
            promptTokens: number;
            reasoningTokens: number | null;
            /** Requestcount */
            requestCount: number;
            /** Taskid */
            taskId: string;
            /** Tokendetailscomplete */
            tokenDetailsComplete: boolean;
            /** Totaltokens */
            totalTokens: number;
            visibleCompletionTokens: number | null;
        };
        /** TokenUsageBreakdown */
        TokenUsageBreakdown: {
            /** Cachedtokens */
            cachedTokens: number;
            /** Completiontokens */
            completionTokens: number;
            /** Prompttokens */
            promptTokens: number;
            /** Totaltokens */
            totalTokens: number;
        };
        /** UpdateChapterRequest */
        UpdateChapterRequest: {
            /** Content */
            content: string;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            /** Title */
            title: string;
        };
        /** UpdateCharacterRequest */
        UpdateCharacterRequest: {
            age?: string | null;
            aliases?: string | null;
            appearance?: string | null;
            background?: string | null;
            behaviorBoundaries?: string | null;
            combatAbility?: string | null;
            coreDesire?: string | null;
            currentStatus?: ("active" | "missing" | "dead" | "imprisoned" | "unknown") | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            factionId?: string | null;
            gender?: string | null;
            identity?: string | null;
            name?: string | null;
            personality?: string | null;
            powerLevel?: string | null;
            relationshipPrinciples?: string | null;
            shortTermGoal?: string | null;
            specialSkills?: string | null;
            speechStyle?: string | null;
            statusNote?: string | null;
        };
        /** UpdateExperienceRequest */
        UpdateExperienceRequest: {
            chapterId?: string | null;
            content?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            order?: number | null;
        };
        /** UpdateFactionRequest */
        UpdateFactionRequest: {
            aliases?: string | null;
            baseId?: string | null;
            description?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            name?: string | null;
            type?: string | null;
        };
        /** UpdateForeshadowingRequest */
        UpdateForeshadowingRequest: {
            expectedPayoff?: string | null;
            name?: string | null;
            payoffAt?: string | null;
            plantedAt?: string | null;
            plantedContent?: string | null;
            status?: ("active" | "paid_off" | "abandoned") | null;
        };
        /** UpdateGlossaryRequest */
        UpdateGlossaryRequest: {
            category?: string | null;
            definition?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            term?: string | null;
        };
        /** UpdateItemRequest */
        UpdateItemRequest: {
            aliases?: string | null;
            description?: string | null;
            effect?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            name?: string | null;
            origin?: string | null;
            ownerId?: string | null;
            rarity?: string | null;
            type?: string | null;
        };
        /** UpdateLocationRequest */
        UpdateLocationRequest: {
            aliases?: string | null;
            climate?: string | null;
            culture?: string | null;
            description?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            name?: string | null;
            parentId?: string | null;
            type?: string | null;
        };
        /** UpdateNovelSummaryRequest */
        UpdateNovelSummaryRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            summary: string | null;
        };
        /** UpdateOutlineNodeRequest */
        UpdateOutlineNodeRequest: {
            actualWordCount?: number | null;
            chapterEndOrder?: number | null;
            chapterStartOrder?: number | null;
            content?: string | null;
            estimatedWordCount?: number | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            kind?: ("stage" | "plot_unit" | "chapter_group") | null;
            linkedChapterId?: string | null;
            order?: number | null;
            parentId?: string | null;
            status?: ("planned" | "in_progress" | "completed" | "skipped") | null;
            title?: string | null;
        };
        /** UpdatePortraitSectionRequest */
        UpdatePortraitSectionRequest: {
            /** Content */
            content: string;
        };
        /** UpdateQualityCheckRequest */
        UpdateQualityCheckRequest: {
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            /**
             * Resetresult
             * @default false
             */
            resetResult: boolean;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "skipped";
        };
        /** UpdateReferenceRequest */
        UpdateReferenceRequest: {
            content?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            sourceUrl?: string | null;
            title?: string | null;
            type?: ("note" | "web" | "book" | "image" | "custom") | null;
        };
        /** UpdateRelationRequest */
        UpdateRelationRequest: {
            description?: string | null;
            endDate?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            intimacy?: number | null;
            relationType?: ("family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other") | null;
            startDate?: string | null;
        };
        /** UpdateVideoEpisodeRequest */
        UpdateVideoEpisodeRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            creativeIntent?: string | null;
            /** Expectedrevision */
            expectedRevision: number;
            targetDurationSeconds?: number | null;
            title?: string | null;
        };
        /** UpdateWritingSessionRequest */
        UpdateWritingSessionRequest: {
            phase?: ("idle" | "discussing" | "generating" | "recording" | "completed") | null;
            title?: string | null;
        };
        /** UserResponse */
        UserResponse: {
            /** Creditbalancemicros */
            creditBalanceMicros: string;
            /** Id */
            id: string;
            maskedPhone?: string | null;
            /** Username */
            username: string;
        };
        /** VerifyPhoneChallengeRequest */
        VerifyPhoneChallengeRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Code */
            code: string;
            /** Phone */
            phone: string;
        };
        /** VersionActionRequest */
        VersionActionRequest: {
            baseVersionId?: string | null;
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Confirmationhash */
            confirmationHash: string;
            documentType: components["schemas"]["DocumentType"];
        };
        /** VersionDetailResponse */
        VersionDetailResponse: {
            appliedAt: string | null;
            /** Artifactkey */
            artifactKey: string;
            baseVersionId: string | null;
            chapterId: string | null;
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            createdByAgent: string | null;
            diff: components["schemas"]["VersionDiffResponse"] | null;
            documentType: components["schemas"]["DocumentType"];
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            payload: components["schemas"]["DocumentVersionPayload"];
            restoredFromVersionId: string | null;
            source: components["schemas"]["VersionSource"];
            sourceOutlineVersionId: string | null;
            status: components["schemas"]["VersionStatus"];
            summary: string | null;
            taskId: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Versionnumber */
            versionNumber: number;
        };
        /** VersionDiffResponse */
        VersionDiffResponse: {
            /** Blocks */
            blocks: components["schemas"]["DiffBlock"][];
            /** Confirmationhash */
            confirmationHash: string;
            fromVersionId: string | null;
            /** Fromwordcount */
            fromWordCount: number;
            toVersionId: string | null;
            /** Towordcount */
            toWordCount: number;
            /** Wordcountdelta */
            wordCountDelta: number;
        };
        /** VersionListItem */
        VersionListItem: {
            appliedAt: string | null;
            baseVersionId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            createdByAgent: string | null;
            documentType: components["schemas"]["DocumentType"];
            /** Id */
            id: string;
            restoredFromVersionId: string | null;
            source: components["schemas"]["VersionSource"];
            sourceOutlineVersionId: string | null;
            status: components["schemas"]["VersionStatus"];
            summary: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Versionnumber */
            versionNumber: number;
            /** Wordcount */
            wordCount: number;
        };
        /** VersionPreviewRequest */
        VersionPreviewRequest: {
            baseVersionId?: string | null;
            chapterId?: string | null;
            documentType: components["schemas"]["DocumentType"];
        };
        /** VersionPreviewResponse */
        VersionPreviewResponse: {
            baseVersionId: string | null;
            chapterId: string | null;
            /** Confirmationhash */
            confirmationHash: string;
            /** Confirmationsummary */
            confirmationSummary: string;
            /** Contenthash */
            contentHash: string;
            diff: components["schemas"]["VersionDiffResponse"];
            /** Dirty */
            dirty: boolean;
            documentType: components["schemas"]["DocumentType"];
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** @enum {string} */
        VersionSource: "agent" | "manual" | "restore";
        /** @enum {string} */
        VersionStatus: "awaiting_user" | "applied";
        /**
         * VideoAssetResponse
         * @description 素材库中可审核、可锁定的真实文件。
         */
        VideoAssetResponse: {
            /**
             * Bytesize
             * Format: int64
             */
            byteSize: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            durationMs: number | null;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "sfx" | "music" | "episode_export";
            /** Id */
            id: string;
            lockedAt: string | null;
            /** Mimetype */
            mimeType: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "image" | "video" | "audio";
            /** Name */
            name: string;
            /** Projectid */
            projectId: string;
            /** Rightsstatus */
            rightsStatus: string;
            /** Sha256 */
            sha256: string;
            /** Sourcekind */
            sourceKind: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeAudioClipInput */
        VideoEpisodeAudioClipInput: {
            /** Assetid */
            assetId: string;
            /**
             * Fadeinms
             * @default 0
             */
            fadeInMs: number;
            /**
             * Fadeoutms
             * @default 0
             */
            fadeOutMs: number;
            /**
             * Gainmillibels
             * @default 0
             */
            gainMillibels: number;
            shotVersionId?: string | null;
            /**
             * Sourceinms
             * @default 0
             */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /** Timelinestartms */
            timelineStartMs: number;
            /**
             * Trackkind
             * @enum {string}
             */
            trackKind: "dialogue" | "narration" | "ambience" | "sfx" | "music";
        };
        /** VideoEpisodeAudioClipResponse */
        VideoEpisodeAudioClipResponse: {
            asset: components["schemas"]["VideoEpisodePostAssetResponse"];
            /** Assetid */
            assetId: string;
            /**
             * Fadeinms
             * @default 0
             */
            fadeInMs: number;
            /**
             * Fadeoutms
             * @default 0
             */
            fadeOutMs: number;
            /**
             * Gainmillibels
             * @default 0
             */
            gainMillibels: number;
            /** Ordinal */
            ordinal: number;
            shotId: string | null;
            shotVersionId?: string | null;
            /**
             * Sourceinms
             * @default 0
             */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /** Timelinestartms */
            timelineStartMs: number;
            /**
             * Trackkind
             * @enum {string}
             */
            trackKind: "dialogue" | "narration" | "ambience" | "sfx" | "music";
        };
        /** VideoEpisodeCommandResponse */
        VideoEpisodeCommandResponse: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            episodeId: string | null;
            /** Operation */
            operation: string;
            /** Resultid */
            resultId: string;
            resultRevision: number | null;
            /**
             * Resulttype
             * @enum {string}
             */
            resultType: "episode" | "episode_list" | "source_set" | "script_draft" | "script_confirmation" | "script_version" | "script_run" | "storyboard_draft" | "storyboard_confirmation" | "storyboard_version" | "storyboard_run" | "take_adoption" | "production_baseline";
        };
        /** VideoEpisodeDeliveryAssetResponse */
        VideoEpisodeDeliveryAssetResponse: {
            /** Bytesize */
            byteSize: number;
            /** Contenturl */
            contentUrl: string;
            /** Durationms */
            durationMs: number;
            /** Id */
            id: string;
            /** Mimetype */
            mimeType: string;
            /**
             * Modality
             * @constant
             */
            modality: "video";
            /** Name */
            name: string;
            /** Sha256 */
            sha256: string;
        };
        /** VideoEpisodeDeliveryResponse */
        VideoEpisodeDeliveryResponse: {
            asset: components["schemas"]["VideoEpisodeDeliveryAssetResponse"];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Editversionid */
            editVersionId: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Inputhash */
            inputHash: string;
            /** Mixversionid */
            mixVersionId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Taskid */
            taskId: string;
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeDependencyInput */
        VideoEpisodeDependencyInput: {
            consumerLineId?: string | null;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Description */
            description: string;
            /** Narrativetime */
            narrativeTime: string;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerscriptversionid */
            producerScriptVersionId: string;
            /** Producerstatekey */
            producerStateKey: string;
        };
        /** VideoEpisodeDependencyResponse */
        VideoEpisodeDependencyResponse: {
            /** Consumerepisodeid */
            consumerEpisodeId: string;
            consumerLineId?: string | null;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Consumerscriptversionid */
            consumerScriptVersionId: string;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Narrativetime */
            narrativeTime: string;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerscriptversionid */
            producerScriptVersionId: string;
            /** Producerstatehash */
            producerStateHash: string;
            /** Producerstatekey */
            producerStateKey: string;
        };
        /** VideoEpisodeDetailResponse */
        VideoEpisodeDetailResponse: {
            /** Candidateartifacts */
            candidateArtifacts: components["schemas"]["VideoEpisodeScriptCandidateResponse"][];
            currentScriptVersion: components["schemas"]["VideoEpisodeScriptVersionResponse"] | null;
            /** Dependencies */
            dependencies: components["schemas"]["VideoEpisodeDependencyResponse"][];
            episode: components["schemas"]["VideoEpisodeResponse"];
            latestScriptRun?: components["schemas"]["VideoEpisodeScriptRunResponse"] | null;
            scriptDraft: components["schemas"]["VideoEpisodeScriptDraftResponse"];
            /** Scriptversions */
            scriptVersions: components["schemas"]["VideoEpisodeScriptVersionResponse"][];
            /** Sourcesets */
            sourceSets: components["schemas"]["VideoEpisodeSourceSetResponse"][];
        };
        /** VideoEpisodeEditClipInput */
        VideoEpisodeEditClipInput: {
            /** Adoptionid */
            adoptionId: string;
            /**
             * Sourceaudiomode
             * @enum {string}
             */
            sourceAudioMode: "keep" | "mute";
            /** Sourceinms */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /** Takeid */
            takeId: string;
            /** Tempkey */
            tempKey: string;
            /**
             * Transitionafter
             * @default cut
             * @enum {string}
             */
            transitionAfter: "cut" | "fade_black";
            /**
             * Transitiondurationms
             * @default 0
             */
            transitionDurationMs: number;
        };
        /** VideoEpisodeEditClipResponse */
        VideoEpisodeEditClipResponse: {
            /** Adoptionid */
            adoptionId: string;
            asset: components["schemas"]["VideoEpisodePostAssetResponse"];
            /** Clipid */
            clipId: string;
            /** Ordinal */
            ordinal: number;
            /** Outputdurationms */
            outputDurationMs: number;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /**
             * Sourceaudiomode
             * @enum {string}
             */
            sourceAudioMode: "keep" | "mute";
            /** Sourceinms */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /** Takeid */
            takeId: string;
            /** Timelinestartms */
            timelineStartMs: number;
            /**
             * Transitionafter
             * @enum {string}
             */
            transitionAfter: "cut" | "fade_black";
            /** Transitiondurationms */
            transitionDurationMs: number;
        };
        /** VideoEpisodeEditVersionListResponse */
        VideoEpisodeEditVersionListResponse: {
            currentVersionId: string | null;
            /** Episodeid */
            episodeId: string;
            /** Headrevision */
            headRevision: number;
            nextBeforeVersionNo: number | null;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Versions */
            versions: components["schemas"]["VideoEpisodeEditVersionSummary"][];
        };
        /** VideoEpisodeEditVersionResponse */
        VideoEpisodeEditVersionResponse: {
            basedOnVersionId: string | null;
            /** Clipcount */
            clipCount: number;
            /** Clips */
            clips: components["schemas"]["VideoEpisodeEditClipResponse"][];
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Headrevision */
            headRevision: number;
            /** Id */
            id: string;
            /** Omissioncount */
            omissionCount: number;
            /** Omissions */
            omissions: components["schemas"]["VideoEpisodeShotOmissionResponse"][];
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Totaldurationms */
            totalDurationMs: number;
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeEditVersionSummary */
        VideoEpisodeEditVersionSummary: {
            basedOnVersionId: string | null;
            /** Clipcount */
            clipCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Omissioncount */
            omissionCount: number;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Totaldurationms */
            totalDurationMs: number;
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeEndingState */
        VideoEpisodeEndingState: {
            /** Description */
            description: string;
            /** Entityids */
            entityIds?: string[];
            /** Key */
            key: string;
            /**
             * Narrativetime
             * @default
             */
            narrativeTime: string;
        };
        /** VideoEpisodeExportTaskResponse */
        VideoEpisodeExportTaskResponse: {
            /** Attemptcount */
            attemptCount: number;
            /** Burnsubtitles */
            burnSubtitles: boolean;
            /** Clientrequestid */
            clientRequestId: string;
            completedAt: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Editversionid */
            editVersionId: string;
            /** Episodeid */
            episodeId: string;
            export: components["schemas"]["VideoEpisodeDeliveryResponse"] | null;
            /**
             * Framespersecond
             * @enum {integer}
             */
            framesPerSecond: 24 | 25 | 30;
            /** Id */
            id: string;
            /** Inputhash */
            inputHash: string;
            lastErrorCode: string | null;
            lastErrorMessage: string | null;
            /** Mixversionid */
            mixVersionId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /**
             * Resolution
             * @enum {string}
             */
            resolution: "720p" | "1080p";
            retryOfTaskId: string | null;
            startedAt: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "rendering" | "succeeded" | "failed";
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeListResponse */
        VideoEpisodeListResponse: {
            /** Episodes */
            episodes: components["schemas"]["VideoEpisodeResponse"][];
            /** Projectid */
            projectId: string;
            /** Projectrevision */
            projectRevision: number;
        };
        /** VideoEpisodeMixVersionListResponse */
        VideoEpisodeMixVersionListResponse: {
            currentVersionId: string | null;
            /** Episodeid */
            episodeId: string;
            /** Headrevision */
            headRevision: number;
            nextBeforeVersionNo: number | null;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Versions */
            versions: components["schemas"]["VideoEpisodeMixVersionSummary"][];
        };
        /** VideoEpisodeMixVersionResponse */
        VideoEpisodeMixVersionResponse: {
            /** Audioclipcount */
            audioClipCount: number;
            /** Audioclips */
            audioClips: components["schemas"]["VideoEpisodeAudioClipResponse"][];
            basedOnVersionId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Editversionid */
            editVersionId: string;
            /** Episodeid */
            episodeId: string;
            /** Headrevision */
            headRevision: number;
            /** Id */
            id: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Subtitlecuecount */
            subtitleCueCount: number;
            /** Subtitlecues */
            subtitleCues: components["schemas"]["VideoEpisodeSubtitleCueResponse"][];
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeMixVersionSummary */
        VideoEpisodeMixVersionSummary: {
            /** Audioclipcount */
            audioClipCount: number;
            basedOnVersionId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Editversionid */
            editVersionId: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Subtitlecuecount */
            subtitleCueCount: number;
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodePostAssetResponse */
        VideoEpisodePostAssetResponse: {
            /** Bytesize */
            byteSize: number;
            /** Durationms */
            durationMs: number;
            /** Id */
            id: string;
            /** Mimetype */
            mimeType: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "video" | "audio";
            /** Name */
            name: string;
            /** Sha256 */
            sha256: string;
        };
        /**
         * VideoEpisodeProductionShotInput
         * @description 制作基线逐镜冻结输入；渲染任务不得从可变 Head 重新拼装。
         */
        VideoEpisodeProductionShotInput: {
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /** Generateaudio */
            generateAudio: boolean;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeSnapshot"][];
            /** Model */
            model: string;
            /**
             * Outputformat
             * @constant
             */
            outputFormat: "mp4";
            /** Prompt */
            prompt: string;
            /** Promptversionid */
            promptVersionId: string;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** References */
            references: components["schemas"]["VideoEpisodeRenderReference"][];
            /**
             * Resolution
             * @constant
             */
            resolution: "720p";
            /**
             * Schemaversion
             * @enum {string}
             */
            schemaVersion: "video-production-shot-input/1.0" | "video-production-shot-input/1.1" | "video-production-shot-input/1.2";
            /** Scriptlineids */
            scriptLineIds?: string[];
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Shotcontenthash */
            shotContentHash: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Shotversionno */
            shotVersionNo: number;
            /** Watermark */
            watermark: boolean;
        };
        /** VideoEpisodeRenderReference */
        VideoEpisodeRenderReference: {
            /** Assetid */
            assetId: string;
            /** Canoncontenthash */
            canonContentHash: string;
            /** Canonversionid */
            canonVersionId: string;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            lockedAt?: string | null;
            /**
             * Mimetype
             * @enum {string}
             */
            mimeType: "image/jpeg" | "image/png" | "image/webp";
            /** Ordinal */
            ordinal: number;
            rightsStatus?: "confirmed" | null;
            /** Sha256 */
            sha256: string;
            /** Strength */
            strength: number;
        };
        /** VideoEpisodeRenderTaskResponse */
        VideoEpisodeRenderTaskResponse: {
            /** Attemptcount */
            attemptCount: number;
            completedAt: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Inputhash */
            inputHash: string;
            inputSnapshot: components["schemas"]["VideoEpisodeProductionShotInput"];
            lastErrorCode: string | null;
            lastErrorMessage: string | null;
            mediaKind: ("provider_media" | "simulated_placeholder") | null;
            /** Model */
            model: string;
            /** Pollcount */
            pollCount: number;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Promptversionid */
            promptVersionId: string;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            providerTaskId: string | null;
            retryOfTaskId: string | null;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "submitting" | "submission_unknown" | "queued" | "running" | "archiving" | "succeeded" | "failed" | "expired" | "cancelled";
            submittedAt: string | null;
            takeId: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeResponse */
        VideoEpisodeResponse: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Creativeintent */
            creativeIntent: string;
            currentProductionBaselineId: string | null;
            currentScriptVersionId: string | null;
            currentSourceSetVersionId: string | null;
            currentStoryboardVersionId: string | null;
            /** Deliveryrevision */
            deliveryRevision: number;
            /** Id */
            id: string;
            latestDeliveryVersionId: string | null;
            /** Novelid */
            novelId: string;
            /** Order */
            order: number;
            /** Productionrevision */
            productionRevision: number;
            /** Projectid */
            projectId: string;
            /** Revision */
            revision: number;
            targetDurationSeconds: number | null;
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeScriptCandidateResponse */
        VideoEpisodeScriptCandidateResponse: {
            /** Artifactid */
            artifactId: string;
            baseScriptVersionId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Episodeid */
            episodeId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            review?: components["schemas"]["VideoEpisodeScriptReview"] | null;
            /** Reviewfindings */
            reviewFindings?: components["schemas"]["VideoEpisodeScriptReviewFinding"][];
            /** Revision */
            revision: number;
            sourceSetVersionId: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "awaiting_user" | "applied" | "rejected";
            summary: string | null;
            /** Title */
            title: string;
            /** Workflowrunid */
            workflowRunId: string;
        };
        /** VideoEpisodeScriptConfirmationResponse */
        VideoEpisodeScriptConfirmationResponse: {
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            /** Confirmationhash */
            confirmationHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Draftrevision */
            draftRevision: number;
            /** Episodeid */
            episodeId: string;
            /** Episoderevision */
            episodeRevision: number;
            sourceSetVersionId: string | null;
        };
        /**
         * VideoEpisodeScriptDocument
         * @description 工作稿和正式版共用完整结构；空工作稿不冒充已经确认的剧本。
         */
        VideoEpisodeScriptDocument: {
            /** Dependencies */
            dependencies?: components["schemas"]["VideoEpisodeDependencyInput"][];
            /** Endingstates */
            endingStates?: components["schemas"]["VideoEpisodeEndingState"][];
            overview?: components["schemas"]["VideoEpisodeScriptOverview"];
            /** Scenes */
            scenes?: components["schemas"]["VideoEpisodeScriptScene"][];
            /**
             * Schemaversion
             * @default video-episode-script/1.0
             * @constant
             */
            schemaVersion: "video-episode-script/1.0";
        };
        /** VideoEpisodeScriptDraftResponse */
        VideoEpisodeScriptDraftResponse: {
            adoptedArtifactId: string | null;
            baseScriptVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Episodeid */
            episodeId: string;
            /** Nodeidmappings */
            nodeIdMappings?: {
                [key: string]: string;
            };
            /** Revision */
            revision: number;
            sourceSetVersionId: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeScriptLine */
        VideoEpisodeScriptLine: {
            id?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "action" | "dialogue" | "narration";
            /** Sourcerefs */
            sourceRefs?: components["schemas"]["VideoEpisodeSourceRef"][];
            speakerId?: string | null;
            tempKey?: string | null;
            /** Text */
            text: string;
        };
        /** VideoEpisodeScriptOverview */
        VideoEpisodeScriptOverview: {
            /**
             * Creativeintent
             * @default
             */
            creativeIntent: string;
            /**
             * Summary
             * @default
             */
            summary: string;
            targetDurationSeconds?: number | null;
        };
        /** VideoEpisodeScriptReview */
        VideoEpisodeScriptReview: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "pass" | "revise";
            /** Findings */
            findings: components["schemas"]["VideoEpisodeScriptReviewFinding"][];
            /** Requiredchanges */
            requiredChanges: string[];
            /** Summary */
            summary: string;
        };
        /** VideoEpisodeScriptReviewFinding */
        VideoEpisodeScriptReviewFinding: {
            /**
             * Code
             * @enum {string}
             */
            code: "source" | "continuity" | "dialogue" | "clarity";
            lineId: string | null;
            /** Message */
            message: string;
            sceneId: string | null;
        };
        /** VideoEpisodeScriptRunResponse */
        VideoEpisodeScriptRunResponse: {
            artifactId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            errorCode: string | null;
            errorMessage: string | null;
            /** Runid */
            runId: string;
            /** Status */
            status: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeScriptScene */
        VideoEpisodeScriptScene: {
            /** Characterids */
            characterIds?: string[];
            id?: string | null;
            /** Lines */
            lines?: components["schemas"]["VideoEpisodeScriptLine"][];
            /** Locationlabel */
            locationLabel: string;
            /** Narrativetime */
            narrativeTime: string;
            tempKey?: string | null;
            /** Timelabel */
            timeLabel: string;
            /** Title */
            title: string;
        };
        /** VideoEpisodeScriptVersionListResponse */
        VideoEpisodeScriptVersionListResponse: {
            /** Versions */
            versions: components["schemas"]["VideoEpisodeScriptVersionResponse"][];
        };
        /** VideoEpisodeScriptVersionResponse */
        VideoEpisodeScriptVersionResponse: {
            basedOnVersionId: string | null;
            /** Confirmationartifactid */
            confirmationArtifactId: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            sourceSetVersionId: string | null;
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeShotOmissionInput */
        VideoEpisodeShotOmissionInput: {
            /** Reason */
            reason: string;
            /** Shotversionid */
            shotVersionId: string;
        };
        /** VideoEpisodeShotOmissionResponse */
        VideoEpisodeShotOmissionResponse: {
            /** Reason */
            reason: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
        };
        /** VideoEpisodeSourceRange */
        VideoEpisodeSourceRange: {
            /** End */
            end: number;
            /** Start */
            start: number;
        };
        /** VideoEpisodeSourceRef */
        VideoEpisodeSourceRef: {
            /** End */
            end: number;
            /** Sourcesnapshotid */
            sourceSnapshotId: string;
            /** Start */
            start: number;
        };
        /** VideoEpisodeSourceSelection */
        VideoEpisodeSourceSelection: {
            /** Chapterid */
            chapterId: string;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            /** Ranges */
            ranges: components["schemas"]["VideoEpisodeSourceRange"][];
            /** Sourcehash */
            sourceHash: string;
        };
        /** VideoEpisodeSourceSetListResponse */
        VideoEpisodeSourceSetListResponse: {
            /** Sourcesets */
            sourceSets: components["schemas"]["VideoEpisodeSourceSetResponse"][];
        };
        /** VideoEpisodeSourceSetResponse */
        VideoEpisodeSourceSetResponse: {
            basedOnVersionId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Sources */
            sources: components["schemas"]["VideoEpisodeSourceSnapshotResponse"][];
            /** Versionno */
            versionNo: number;
        };
        /** VideoEpisodeSourceSnapshotResponse */
        VideoEpisodeSourceSnapshotResponse: {
            /** Chapterid */
            chapterId: string;
            /** Chaptertitle */
            chapterTitle: string;
            /**
             * Chapterupdatedat
             * Format: date-time
             */
            chapterUpdatedAt: string;
            currentChapterContentHash?: string | null;
            currentChapterUpdatedAt?: string | null;
            /** Id */
            id: string;
            /** Ranges */
            ranges: components["schemas"]["VideoEpisodeSourceRange"][];
            /** Sourcehash */
            sourceHash: string;
            /**
             * Sourcestatus
             * @default unknown
             * @enum {string}
             */
            sourceStatus: "current" | "updated" | "missing" | "unknown";
            /** Sourcetext */
            sourceText: string;
        };
        /** VideoEpisodeSubtitleCueInput */
        VideoEpisodeSubtitleCueInput: {
            /** Endms */
            endMs: number;
            /** Scriptlineid */
            scriptLineId: string;
            /** Shotversionid */
            shotVersionId: string;
            speaker?: string | null;
            /** Startms */
            startMs: number;
            /** Text */
            text: string;
        };
        /** VideoEpisodeSubtitleCueResponse */
        VideoEpisodeSubtitleCueResponse: {
            /** Endms */
            endMs: number;
            /** Ordinal */
            ordinal: number;
            /** Scriptlineid */
            scriptLineId: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            speaker?: string | null;
            /** Startms */
            startMs: number;
            /** Text */
            text: string;
        };
        /** VideoImpactDecision */
        VideoImpactDecision: {
            /**
             * Action
             * @enum {string}
             */
            action: "keep_existing" | "revise_target" | "not_applicable" | "defer";
            /** Itemid */
            itemId: string;
            /**
             * Note
             * @default
             */
            note: string;
        };
        /** VideoImpactReviewItem */
        VideoImpactReviewItem: {
            afterState: components["schemas"]["VideoImpactStateSnapshot"] | null;
            afterStateHash?: string | null;
            beforeState: components["schemas"]["VideoImpactStateSnapshot"];
            /** Beforestatehash */
            beforeStateHash: string;
            /**
             * Changetype
             * @enum {string}
             */
            changeType: "changed" | "removed";
            consumerLineId: string | null;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Dependencyid */
            dependencyId: string;
            /** Description */
            description: string;
            /** Itemhash */
            itemHash: string;
            /** Itemid */
            itemId: string;
            /**
             * Kind
             * @constant
             */
            kind: "direct_dependency_changed";
            /** Narrativetime */
            narrativeTime: string;
            /** Producerstatekey */
            producerStateKey: string;
        };
        /** VideoImpactReviewListResponse */
        VideoImpactReviewListResponse: {
            nextBeforeReviewId: string | null;
            /** Reviews */
            reviews: components["schemas"]["VideoImpactReviewSummaryResponse"][];
        };
        /** VideoImpactReviewReport */
        VideoImpactReviewReport: {
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /** Items */
            items: components["schemas"]["VideoImpactReviewItem"][];
            /**
             * Kind
             * @constant
             */
            kind: "explicit_dependency_changed";
            producerBaselineId: string | null;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /**
             * Requiresauthorreview
             * @constant
             */
            requiresAuthorReview: true;
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "video-impact-review/1.0";
            targetBaselineId: string | null;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
        };
        /** VideoImpactReviewResponse */
        VideoImpactReviewResponse: {
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Decisioncount */
            decisionCount: number;
            /** Decisions */
            decisions: components["schemas"]["VideoImpactDecision"][];
            /** Id */
            id: string;
            /** Isstale */
            isStale: boolean;
            /** Itemcount */
            itemCount: number;
            producerBaselineId: string | null;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /** Projectid */
            projectId: string;
            report: components["schemas"]["VideoImpactReviewReport"];
            /** Revision */
            revision: number;
            /** Stalereasons */
            staleReasons: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "resolved";
            targetBaselineId: string | null;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoImpactReviewSummaryResponse */
        VideoImpactReviewSummaryResponse: {
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Decisioncount */
            decisionCount: number;
            /** Id */
            id: string;
            /** Isstale */
            isStale: boolean;
            /** Itemcount */
            itemCount: number;
            producerBaselineId: string | null;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /** Projectid */
            projectId: string;
            /** Revision */
            revision: number;
            /** Stalereasons */
            staleReasons: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "resolved";
            targetBaselineId: string | null;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoImpactStateSnapshot */
        VideoImpactStateSnapshot: {
            /** Description */
            description: string;
            /** Entityids */
            entityIds?: string[];
            /** Key */
            key: string;
            /** Narrativetime */
            narrativeTime: string;
        };
        /** VideoProductionBaselineAdoptionInput */
        VideoProductionBaselineAdoptionInput: {
            /** Adoptionid */
            adoptionId: string;
            /** Shotversionid */
            shotVersionId: string;
        };
        /** VideoProductionBaselineListResponse */
        VideoProductionBaselineListResponse: {
            /** Baselines */
            baselines: components["schemas"]["VideoProductionBaselineSummary"][];
            nextBeforeVersionNo: number | null;
        };
        /** VideoProductionBaselineManifest */
        VideoProductionBaselineManifest: {
            /** Episodeid */
            episodeId: string;
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "video-production-baseline/1.0";
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shots */
            shots: components["schemas"]["VideoProductionBaselineManifestShot"][];
            /** Storyboardversionid */
            storyboardVersionId: string;
        };
        /** VideoProductionBaselineManifestShot */
        VideoProductionBaselineManifestShot: {
            adoptionId: string | null;
            /** Inputhash */
            inputHash: string;
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
        };
        /** VideoProductionBaselineResponse */
        VideoProductionBaselineResponse: {
            basedOnBaselineId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            manifest: components["schemas"]["VideoProductionBaselineManifest"];
            /** Productionrevision */
            productionRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Shots */
            shots: components["schemas"]["VideoProductionBaselineShotResponse"][];
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Versionno */
            versionNo: number;
        };
        /** VideoProductionBaselineShotResponse */
        VideoProductionBaselineShotResponse: {
            adoptionId: string | null;
            /** Inputhash */
            inputHash: string;
            inputSnapshot: components["schemas"]["VideoProductionShotInputSnapshot"];
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "adopted";
        };
        /** VideoProductionBaselineSummary */
        VideoProductionBaselineSummary: {
            basedOnBaselineId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Versionno */
            versionNo: number;
        };
        /** VideoProductionCapabilityResponse */
        VideoProductionCapabilityResponse: {
            /** Alloweddurationseconds */
            allowedDurationSeconds: number[];
            /**
             * Allowedoutputformat
             * @constant
             */
            allowedOutputFormat: "mp4";
            /**
             * Allowedresolution
             * @constant
             */
            allowedResolution: "720p";
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmationrequired */
            feeConfirmationRequired: boolean;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /**
             * Maximagereferences
             * @constant
             */
            maxImageReferences: 20;
            /** Model */
            model: string;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Providerconfigured */
            providerConfigured: boolean;
            /** Providerenabled */
            providerEnabled: boolean;
            /** Videopreviewenabled */
            videoPreviewEnabled: boolean;
        };
        /** VideoProductionKeyframeInput */
        VideoProductionKeyframeInput: {
            /** Assetid */
            assetId: string;
            /**
             * Role
             * @enum {string}
             */
            role: "initial_state" | "transition_anchor" | "end_state";
            /** Shotversionid */
            shotVersionId: string;
        };
        /** VideoProductionKeyframeSnapshot */
        VideoProductionKeyframeSnapshot: {
            /** Assetid */
            assetId: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "storyboard" | "keyframe";
            /** Keyframeversionid */
            keyframeVersionId: string;
            lockedAt?: string | null;
            /**
             * Mimetype
             * @enum {string}
             */
            mimeType: "image/jpeg" | "image/png" | "image/webp";
            /** Ordinal */
            ordinal: number;
            rightsStatus?: "confirmed" | null;
            /**
             * Role
             * @enum {string}
             */
            role: "initial_state" | "transition_anchor" | "end_state";
            /** Sha256 */
            sha256: string;
        };
        /** VideoProductionShotInputSnapshot */
        VideoProductionShotInputSnapshot: {
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /** Generateaudio */
            generateAudio: boolean;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeSnapshot"][];
            /** Model */
            model: string;
            /**
             * Outputformat
             * @constant
             */
            outputFormat: "mp4";
            /** Prompt */
            prompt: string;
            /** Promptversionid */
            promptVersionId: string;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** References */
            references: components["schemas"]["VideoShotReferenceInput"][];
            /**
             * Resolution
             * @constant
             */
            resolution: "720p";
            /**
             * Schemaversion
             * @enum {string}
             */
            schemaVersion: "video-production-shot-input/1.0" | "video-production-shot-input/1.1" | "video-production-shot-input/1.2";
            /** Scriptlineids */
            scriptLineIds: string[];
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Shotcontenthash */
            shotContentHash: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Shotversionno */
            shotVersionNo: number;
            /** Watermark */
            watermark: boolean;
        };
        /**
         * VideoProjectDetailResponse
         * @description 章节影视化工作台加载项目素材所需的公共信息。
         */
        VideoProjectDetailResponse: {
            /** Assets */
            assets: components["schemas"]["VideoAssetResponse"][];
            /** Previewenabled */
            previewEnabled: boolean;
            project: components["schemas"]["VideoProjectResponse"];
            /** Seedanceconfigured */
            seedanceConfigured: boolean;
            /** Seedanceenabled */
            seedanceEnabled: boolean;
        };
        /**
         * VideoProjectListResponse
         * @description 项目列表及创建第一个项目前也必须可见的能力状态。
         */
        VideoProjectListResponse: {
            /** Previewenabled */
            previewEnabled: boolean;
            /** Projects */
            projects: components["schemas"]["VideoProjectResponse"][];
            /** Seedanceconfigured */
            seedanceConfigured: boolean;
            /** Seedanceenabled */
            seedanceEnabled: boolean;
        };
        /**
         * VideoProjectResponse
         * @description 视频项目列表项。
         */
        VideoProjectResponse: {
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Mode */
            mode: string;
            /** Novelid */
            novelId: string;
            /** Provider */
            provider: string;
            /** Revision */
            revision: number;
            /** Status */
            status: string;
            /** Targetaspectratio */
            targetAspectRatio: string;
            /** Targetlanguage */
            targetLanguage: string;
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoShotLineageInput */
        VideoShotLineageInput: {
            /**
             * Relation
             * @enum {string}
             */
            relation: "replacement" | "copy" | "split" | "merge";
            /** Sourceshotid */
            sourceShotId: string;
        };
        /** VideoShotProductionIntent */
        VideoShotProductionIntent: {
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /**
             * Generateaudio
             * @default true
             */
            generateAudio: boolean;
            /**
             * Generationmode
             * @default reference
             * @constant
             */
            generationMode: "reference";
            /** Model */
            model: string;
            /**
             * Outputformat
             * @default mp4
             * @constant
             */
            outputFormat: "mp4";
            /** Prompt */
            prompt: string;
            /**
             * Provider
             * @default seedance
             * @constant
             */
            provider: "seedance";
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** References */
            references: components["schemas"]["VideoShotReferenceInput"][];
            /**
             * Resolution
             * @default 720p
             * @constant
             */
            resolution: "720p";
            /**
             * Watermark
             * @default false
             */
            watermark: boolean;
        };
        /** VideoShotReferenceInput */
        VideoShotReferenceInput: {
            assetId?: string | null;
            canonContentHash?: string | null;
            /** Canonversionid */
            canonVersionId: string;
            duty?: ("identity" | "costume" | "scene" | "prop") | null;
            lockedAt?: string | null;
            mimeType?: ("image/jpeg" | "image/png" | "image/webp") | null;
            ordinal?: number | null;
            rightsStatus?: "confirmed" | null;
            sha256?: string | null;
            strength?: number | null;
        };
        /** VideoShotVersionResponse */
        VideoShotVersionResponse: {
            content: components["schemas"]["VideoStoryboardShot"];
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Ordinal */
            ordinal: number;
            /** Scriptlineids */
            scriptLineIds: string[];
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Shotid */
            shotId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Versionno */
            versionNo: number;
        };
        /** VideoStoryboardCandidateResponse */
        VideoStoryboardCandidateResponse: {
            /** Artifactid */
            artifactId: string;
            baseStoryboardVersionId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Episodeid */
            episodeId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            review?: components["schemas"]["VideoStoryboardReview"] | null;
            /** Reviewfindings */
            reviewFindings?: components["schemas"]["VideoStoryboardReviewFinding"][];
            /** Revision */
            revision: number;
            /** Scriptversionid */
            scriptVersionId: string;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "awaiting_user" | "applied" | "rejected";
            summary: string | null;
            /** Title */
            title: string;
            /** Workflowrunid */
            workflowRunId: string;
        };
        /** VideoStoryboardConfirmationResponse */
        VideoStoryboardConfirmationResponse: {
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            baseStoryboardVersionId: string | null;
            /** Confirmationhash */
            confirmationHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Draftrevision */
            draftRevision: number;
            /** Episodeid */
            episodeId: string;
            /** Episoderevision */
            episodeRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
        };
        /** VideoStoryboardDocument */
        VideoStoryboardDocument: {
            /**
             * Schemaversion
             * @default video-episode-storyboard/1.0
             * @constant
             */
            schemaVersion: "video-episode-storyboard/1.0";
            /** Shots */
            shots?: components["schemas"]["VideoStoryboardShot"][];
        };
        /** VideoStoryboardDraftResponse */
        VideoStoryboardDraftResponse: {
            baseStoryboardVersionId: string | null;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Episodeid */
            episodeId: string;
            /** Revision */
            revision: number;
            scriptVersionId: string | null;
            /** Shotidmappings */
            shotIdMappings?: {
                [key: string]: string;
            };
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoStoryboardReview */
        VideoStoryboardReview: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "pass" | "revise";
            /** Findings */
            findings: components["schemas"]["VideoStoryboardReviewFinding"][];
            /** Requiredchanges */
            requiredChanges: string[];
            /** Summary */
            summary: string;
        };
        /** VideoStoryboardReviewFinding */
        VideoStoryboardReviewFinding: {
            /**
             * Code
             * @enum {string}
             */
            code: "script_coverage" | "continuity" | "shot_clarity" | "feasibility" | "reference" | "duration";
            /** Message */
            message: string;
            scriptSceneId: string | null;
            shotId: string | null;
        };
        /** VideoStoryboardRunListResponse */
        VideoStoryboardRunListResponse: {
            nextBeforeRunId: string | null;
            /** Runs */
            runs: components["schemas"]["VideoStoryboardRunResponse"][];
        };
        /** VideoStoryboardRunResponse */
        VideoStoryboardRunResponse: {
            artifactId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            errorCode: string | null;
            errorMessage: string | null;
            /** Runid */
            runId: string;
            /** Status */
            status: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoStoryboardShot */
        VideoStoryboardShot: {
            /** Action */
            action: string;
            /**
             * Cameramovement
             * @enum {string}
             */
            cameraMovement: "static" | "pan" | "tilt" | "dolly" | "truck" | "crane" | "handheld" | "orbit" | "zoom";
            /** Durationms */
            durationMs: number;
            /**
             * Framing
             * @enum {string}
             */
            framing: "extreme_wide" | "wide" | "medium" | "close_up" | "detail" | "over_shoulder" | "pov";
            id?: string | null;
            /** Lineage */
            lineage?: components["schemas"]["VideoShotLineageInput"][];
            productionIntent: components["schemas"]["VideoShotProductionIntent"];
            /** Scriptlineids */
            scriptLineIds?: string[];
            /** Scriptsceneid */
            scriptSceneId: string;
            tempKey?: string | null;
            /** Title */
            title: string;
        };
        /** VideoStoryboardVersionListResponse */
        VideoStoryboardVersionListResponse: {
            nextBeforeVersionNo: number | null;
            /** Versions */
            versions: components["schemas"]["VideoStoryboardVersionSummary"][];
        };
        /** VideoStoryboardVersionResponse */
        VideoStoryboardVersionResponse: {
            basedOnVersionId: string | null;
            /** Confirmationartifactid */
            confirmationArtifactId: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Shots */
            shots: components["schemas"]["VideoShotVersionResponse"][];
            /** Versionno */
            versionNo: number;
        };
        /** VideoStoryboardVersionSummary */
        VideoStoryboardVersionSummary: {
            basedOnVersionId: string | null;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Versionno */
            versionNo: number;
        };
        /** VideoTakeAdoptionComparison */
        VideoTakeAdoptionComparison: {
            /** Directinputsunchanged */
            directInputsUnchanged: boolean;
            /** Referencehasheschecked */
            referenceHashesChecked?: string[];
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Summary */
            summary: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
        };
        /** VideoTakeAdoptionResponse */
        VideoTakeAdoptionResponse: {
            comparison: components["schemas"]["VideoTakeAdoptionComparison"];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Decisionhash */
            decisionHash: string;
            /** Episodeid */
            episodeId: string;
            /** Id */
            id: string;
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Sourcetakeid */
            sourceTakeId: string;
            /** Targetshotid */
            targetShotId: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
        };
        /** VideoTakeCandidateListResponse */
        VideoTakeCandidateListResponse: {
            /** Episodeid */
            episodeId: string;
            nextBeforeTakeId: string | null;
            /** Takes */
            takes: components["schemas"]["VideoTakeCandidateSummary"][];
            /** Targetshotversionid */
            targetShotVersionId: string;
        };
        /** VideoTakeCandidateSummary */
        VideoTakeCandidateSummary: {
            /** Adopted */
            adopted: boolean;
            adoptionId: string | null;
            /** Assetid */
            assetId: string;
            /** Bytesize */
            byteSize: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Durationms */
            durationMs: number;
            height?: number | null;
            /** Id */
            id: string;
            /** Inputhash */
            inputHash: string;
            lastFrameAssetId: string | null;
            /**
             * Mimetype
             * @constant
             */
            mimeType: "video/mp4";
            /** Model */
            model: string;
            /** Promptversionid */
            promptVersionId: string;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Sourceshotid */
            sourceShotId: string;
            /** Sourceshotversionid */
            sourceShotVersionId: string;
            /** Takeno */
            takeNo: number;
            width?: number | null;
        };
        /** VisualCanonLibraryResponse */
        VisualCanonLibraryResponse: {
            /** Canons */
            canons: components["schemas"]["VisualCanonResponse"][];
        };
        /** VisualCanonResponse */
        VisualCanonResponse: {
            candidateAsset: components["schemas"]["VideoAssetResponse"] | null;
            candidateDefaultStrength: number | null;
            /** Candidateexcludefeatures */
            candidateExcludeFeatures: string[];
            /** Candidateincludefeatures */
            candidateIncludeFeatures: string[];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            currentVersionId: string | null;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Novelid */
            novelId: string;
            /** Projectid */
            projectId: string;
            /** Revision */
            revision: number;
            /** Settingid */
            settingId: string;
            /**
             * Settingkind
             * @enum {string}
             */
            settingKind: "character" | "location" | "item";
            /** Settingname */
            settingName: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Variantkey */
            variantKey: string;
            /** Versions */
            versions: components["schemas"]["VisualCanonVersionResponse"][];
        };
        /** VisualCanonVersionResponse */
        VisualCanonVersionResponse: {
            asset: components["schemas"]["VideoAssetResponse"];
            /** Canonid */
            canonId: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Defaultstrength */
            defaultStrength: number;
            /** Excludefeatures */
            excludeFeatures: string[];
            /** Id */
            id: string;
            /** Includefeatures */
            includeFeatures: string[];
            /** Label */
            label: string;
            /** Settingname */
            settingName: string;
            /** Versionno */
            versionNo: number;
        };
        /** WorkflowArtifactSnapshot */
        WorkflowArtifactSnapshot: {
            /** Actionable */
            actionable: boolean;
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            reviewAvailability?: ("complete" | "partial" | "unavailable") | null;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "under_review" | "awaiting_user" | "applying" | "applied";
        };
        /** WorkflowClarificationSnapshot */
        WorkflowClarificationSnapshot: {
            /** Clarificationcode */
            clarificationCode: string;
            /** Decisionstepid */
            decisionStepId: string;
            /** Prompt */
            prompt: string;
        };
        /** WorkflowCurrentStepSnapshot */
        WorkflowCurrentStepSnapshot: {
            /** Attemptcount */
            attemptCount: number;
            errorCode?: string | null;
            /** Fencingtoken */
            fencingToken: number;
            /**
             * Lane
             * @enum {string}
             */
            lane: "control" | "interactive" | "creative" | "batch_media";
            latestProgress: components["schemas"]["WorkflowStepProgressSnapshot"] | null;
            modelProfile: components["schemas"]["ModelProfileRef"] | null;
            /** Ordinal */
            ordinal: number;
            /** Purpose */
            purpose: string;
            resolvedModel: components["schemas"]["ResolvedModelRef"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running" | "completed" | "failed" | "skipped";
            /** Stepid */
            stepId: string;
        };
        /** WorkflowErrorSnapshot */
        WorkflowErrorSnapshot: {
            /** Errorcode */
            errorCode: string;
            failedStepId?: string | null;
            /** Outcomeunknown */
            outcomeUnknown: boolean;
        };
        /** WorkflowRunDetailResponse */
        WorkflowRunDetailResponse: {
            /** Content */
            content: string;
            summary: components["schemas"]["WorkflowRunSummary"];
        };
        /** WorkflowRunListResponse */
        WorkflowRunListResponse: {
            /** Runs */
            runs: components["schemas"]["WorkflowRunSummary"][];
        };
        /** WorkflowRunSummary */
        WorkflowRunSummary: {
            chapterId: string | null;
            /** Endedat */
            endedAt: string;
            /** Novelid */
            novelId: string;
            /** Runid */
            runId: string;
            /** Runkind */
            runKind: string;
            /** Startedat */
            startedAt: string;
            /** Status */
            status: string;
            /** Taskid */
            taskId: string;
            /** Userid */
            userId: string;
        };
        /** WorkflowStepProgressSnapshot */
        WorkflowStepProgressSnapshot: {
            /** Elapsedseconds */
            elapsedSeconds: number;
            /**
             * Phase
             * @enum {string}
             */
            phase: "preparing" | "waiting_provider" | "validating" | "reporting";
            /** Progresssequence */
            progressSequence: number;
            /**
             * Usagestatus
             * @enum {string}
             */
            usageStatus: "complete" | "partial" | "unknown";
            /** Waitingonprovider */
            waitingOnProvider: boolean;
        };
        /** WorkspaceBootstrapResponse */
        WorkspaceBootstrapResponse: {
            /** Chapters */
            chapters: components["schemas"]["WorkspaceChapterSummary"][];
            currentChapter: components["schemas"]["WorkspaceChapter"] | null;
            currentChapterId: string | null;
            novel: components["schemas"]["WorkspaceNovel"];
        };
        /** WorkspaceChapter */
        WorkspaceChapter: {
            approvedBeatPlan: components["schemas"]["BeatPlanDto"] | null;
            completedAt: string | null;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Order */
            order: number;
            progress: components["schemas"]["ChapterProgressDto"] | null;
            /** Qualitychecks */
            qualityChecks: components["schemas"]["QualityCheckDto"][];
            status: components["schemas"]["ChapterStatus"];
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Wordcount */
            wordCount: number;
        };
        /** WorkspaceChapterSummary */
        WorkspaceChapterSummary: {
            approvedBeatPlan: components["schemas"]["ApprovedBeatPlanSummary"] | null;
            /** Id */
            id: string;
            /** Order */
            order: number;
            status: components["schemas"]["ChapterStatus"];
            /** Title */
            title: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Wordcount */
            wordCount: number;
        };
        /** WorkspaceLoreResponse */
        WorkspaceLoreResponse: {
            /** Characters */
            characters: components["schemas"]["CharacterDto"][];
            /** Factions */
            factions: components["schemas"]["FactionDto"][];
            /** Glossaries */
            glossaries: components["schemas"]["GlossaryDto"][];
            /** Items */
            items: components["schemas"]["ItemDto"][];
            /** Locations */
            locations: components["schemas"]["LocationDto"][];
        };
        /** WorkspaceNovel */
        WorkspaceNovel: {
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
            appliedStyleId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            storyLengthProfile?: components["schemas"]["StoryLengthProfile"] | null;
            storyProgress: string | null;
            summary: string | null;
            targetTotalWordCount?: number | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WorkspacePlanningResponse */
        WorkspacePlanningResponse: {
            outline: components["schemas"]["ContentDto"] | null;
            /** Outlinenodes */
            outlineNodes: components["schemas"]["OutlineNodeDto"][];
            plotProgress: components["schemas"]["PlotProgressDto"] | null;
            storyBackground: components["schemas"]["ContentDto"] | null;
            storyProgress: string | null;
            /**
             * Storyprogressupdatedat
             * Format: date-time
             */
            storyProgressUpdatedAt: string;
            worldSetting: components["schemas"]["ContentDto"] | null;
            writingBible: components["schemas"]["WritingBibleDto"] | null;
        };
        /** WorkspaceResourcesResponse */
        WorkspaceResourcesResponse: {
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
            /** References */
            references: components["schemas"]["ReferenceDto"][];
            /** Styles */
            styles: components["schemas"]["StyleSummary"][];
        };
        /** WorkspaceResponse */
        WorkspaceResponse: {
            /** Chapters */
            chapters: components["schemas"]["WorkspaceChapter"][];
            /** Characters */
            characters: components["schemas"]["CharacterDto"][];
            currentChapterId: string | null;
            /** Factions */
            factions: components["schemas"]["FactionDto"][];
            /** Glossaries */
            glossaries: components["schemas"]["GlossaryDto"][];
            /** Items */
            items: components["schemas"]["ItemDto"][];
            /** Locations */
            locations: components["schemas"]["LocationDto"][];
            novel: components["schemas"]["WorkspaceNovel"];
            outline: components["schemas"]["ContentDto"] | null;
            /** Outlinenodes */
            outlineNodes: components["schemas"]["OutlineNodeDto"][];
            plotProgress: components["schemas"]["PlotProgressDto"] | null;
            /** References */
            references: components["schemas"]["ReferenceDto"][];
            storyBackground: components["schemas"]["ContentDto"] | null;
            /** Styles */
            styles: components["schemas"]["StyleSummary"][];
            worldSetting: components["schemas"]["ContentDto"] | null;
            writingBible: components["schemas"]["WritingBibleDto"] | null;
        };
        /** WritingBibleDto */
        WritingBibleDto: {
            appealModel: string | null;
            comparableTitles: string | null;
            coreSellingPoint: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            genre: string | null;
            /** Id */
            id: string;
            notes: string | null;
            readerPromise: string | null;
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            taboo: string | null;
            targetReaders: string | null;
            targetTotalWordCount: number | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingBibleRequest */
        WritingBibleRequest: {
            appealModel?: string | null;
            comparableTitles?: string | null;
            coreSellingPoint?: string | null;
            expectedUpdatedAt: string | null;
            genre?: string | null;
            notes?: string | null;
            readerPromise?: string | null;
            storyLengthProfile?: ("short_medium" | "long_serial") | null;
            taboo?: string | null;
            targetReaders?: string | null;
            targetTotalWordCount?: number | null;
        };
        /** WritingBibleResponse */
        WritingBibleResponse: {
            appealModel?: string | null;
            comparableTitles?: string | null;
            coreSellingPoint?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            genre?: string | null;
            /** Id */
            id: string;
            notes?: string | null;
            readerPromise?: string | null;
            /**
             * Storylengthprofile
             * @enum {string}
             */
            storyLengthProfile: "short_medium" | "long_serial";
            taboo?: string | null;
            targetReaders?: string | null;
            targetTotalWordCount?: number | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /**
         * Format: binary
         * @description 持续输出写作运行事件的 SSE 字节流
         */
        WritingEventStream: string;
        /** WritingRunCheckpointResponse */
        WritingRunCheckpointResponse: {
            /** Eventsequence */
            eventSequence: number;
            operationStage: string | null;
            operationStep: string | null;
            /** Phase */
            phase: string;
        };
        /** WritingRunListItem */
        WritingRunListItem: {
            activeArtifactId: string | null;
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Novelid */
            novelId: string;
            operation: string | null;
            outcome: components["schemas"]["WritingRunOutcome"];
            /** Phase */
            phase: string;
            /** Recoverable */
            recoverable: boolean;
            /** Runid */
            runId: string;
            /** Scope */
            scope: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Target */
            target: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Taskid */
            taskId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /**
             * Workflow
             * @enum {string}
             */
            workflow: "long_serial" | "short_medium";
            writingSessionId: string | null;
        };
        /** WritingRunListResponse */
        WritingRunListResponse: {
            /** Items */
            items: components["schemas"]["WritingRunPublicListItem"][];
            nextCursor: string | null;
        };
        /** WritingRunOutcome */
        WritingRunOutcome: {
            /** Code */
            code: string;
            currentCommand: components["schemas"]["WritingRunOutcomeCommand"] | null;
            /**
             * Observedat
             * Format: date-time
             */
            observedAt: string;
            /** Reconciliationrequired */
            reconciliationRequired: boolean;
            result: components["schemas"]["WritingRunOutcomeResult"];
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "waiting_user" | "succeeded" | "failed" | "cancelled" | "inconsistent";
            /** Streamshouldclose */
            streamShouldClose: boolean;
            /** Taskterminal */
            taskTerminal: boolean;
        };
        /** WritingRunOutcomeCommand */
        WritingRunOutcomeCommand: {
            /** Id */
            id: string;
            /** Kind */
            kind: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingRunOutcomeResult */
        WritingRunOutcomeResult: {
            id?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "none" | "review_artifact" | "short_candidate" | "check_report" | "final_message";
            /** Ready */
            ready: boolean;
        };
        WritingRunPublicListItem: components["schemas"]["WritingRunListItem"] | components["schemas"]["WritingRunV2Response"];
        /** WritingRunResponse */
        WritingRunResponse: {
            /** Chapterid */
            chapterId: string;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Phase */
            phase: string;
            /** Runid */
            runId: string;
            /** Selectedagents */
            selectedAgents: string[];
            /** Targetwordcount */
            targetWordCount: number;
            /** Taskid */
            taskId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            writingSessionId: string | null;
        };
        WritingRunStartResponse: components["schemas"]["WritingRunResponse"] | components["schemas"]["WritingRunV2Response"];
        WritingRunStatusPublicResponse: components["schemas"]["WritingRunStatusResponse"] | components["schemas"]["WritingRunV2Response"];
        /** WritingRunStatusResponse */
        WritingRunStatusResponse: {
            activeArtifactId?: string | null;
            candidateVersionId: string | null;
            /** Chapterid */
            chapterId: string;
            checkReport: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            checkpoint?: components["schemas"]["WritingRunCheckpointResponse"] | null;
            commandId: string | null;
            commandStatus: ("pending" | "submitted" | "processing" | "succeeded" | "failed") | null;
            createdAt?: string | null;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            error: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Novelid */
            novelId: string;
            operation: ("generate_outline" | "generate_manuscript" | "replace_selection" | "full_check" | "plan_chapter" | "rewrite_scene" | "rewrite_chapter_selection" | "rewrite_outline_selection" | "write_chapter" | "review_chapter") | null;
            outcome: components["schemas"]["WritingRunOutcome"];
            /** Phase */
            phase: string;
            /**
             * Recoverable
             * @default false
             */
            recoverable: boolean;
            reviewReport?: string | null;
            /** Runid */
            runId: string;
            scope?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            target?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Taskid */
            taskId: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /**
             * Workflow
             * @default long_serial
             * @enum {string}
             */
            workflow: "long_serial" | "short_medium";
            writingSessionId?: string | null;
        };
        /** WritingRunV2Response */
        WritingRunV2Response: {
            /** Activesteps */
            activeSteps: components["schemas"]["WorkflowCurrentStepSnapshot"][];
            artifact?: components["schemas"]["WorkflowArtifactSnapshot"] | null;
            cancelRequestedAt?: string | null;
            candidateVersionId?: string | null;
            chapterId: string | null;
            checkReport?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            clarification?: components["schemas"]["WorkflowClarificationSnapshot"] | null;
            /**
             * Commandid
             * @enum {string}
             */
            commandId: null;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: null;
            currentStep?: components["schemas"]["WorkflowCurrentStepSnapshot"] | null;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 2;
            error?: components["schemas"]["WorkflowErrorSnapshot"] | null;
            /** Lasteventsequence */
            lastEventSequence: number;
            operation?: string | null;
            reviewReport?: string | null;
            /** Revision */
            revision: number;
            /** Runid */
            runId: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running" | "waiting_user" | "completed" | "failed" | "cancelled";
            taskId: string | null;
            /** Workflow */
            workflow: string;
        };
        /** WritingSessionDetail */
        WritingSessionDetail: {
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            currentTask: components["schemas"]["WritingTaskSummary"] | null;
            /** Id */
            id: string;
            lastTask: components["schemas"]["WritingTaskSummary"] | null;
            /** Messages */
            messages: components["schemas"]["MessageResponse"][];
            /** Novelid */
            novelId: string;
            /** Phase */
            phase: string;
            title: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingSessionListItem */
        WritingSessionListItem: {
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            lastMessage: components["schemas"]["LastMessageResponse"] | null;
            /** Messagecount */
            messageCount: number;
            /** Novelid */
            novelId: string;
            /** Phase */
            phase: string;
            title: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingSessionResponse */
        WritingSessionResponse: {
            /** Chapterid */
            chapterId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Phase */
            phase: string;
            title: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingTaskSummary */
        WritingTaskSummary: {
            activeArtifactId: string | null;
            currentOperation: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Hasawaitingreviewartifact */
            hasAwaitingReviewArtifact: boolean;
            /** Id */
            id: string;
            operationStage: string | null;
            /** Phase */
            phase: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_phone_challenge_api_v1_auth_phone_challenges_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePhoneChallengeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhoneChallengeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    verify_phone_challenge_api_v1_auth_phone_challenges__challenge_id__verify_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                challenge_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerifyPhoneChallengeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhoneLoginResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    register_api_v1_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_summary_api_v1_billing_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingSummaryResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_usage_api_v1_billing_usage_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BillingUsageResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_task_usage_api_v1_billing_usage_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaskModelUsageResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_chapter_api_v1_chapters__chapter_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                chapter_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceChapter"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_chapter_api_v1_chapters__chapter_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                chapter_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateChapterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterMutationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_chapter_progress_api_v1_chapters__chapter_id__progress_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                chapter_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChapterProgressRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterMutationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_chapter_status_api_v1_chapters__chapter_id__status_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                chapter_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChapterStatusRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterStatusResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_dashboard_api_v1_dashboard_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_workflow_runs_api_v1_debug_workflow_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowRunListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workflow_run_api_v1_debug_workflow_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkflowRunDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    live_api_v1_health_live_get: {
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
                    "application/json": components["schemas"]["LiveHealthResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    ready_api_v1_health_ready_get: {
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
                    "application/json": components["schemas"]["ReadyHealthResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 应用尚未就绪 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadyHealthResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_novels_api_v1_novels_get: {
        parameters: {
            query?: {
                storyLengthProfile?: components["schemas"]["StoryLengthProfile"] | null;
            };
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NovelResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_novel_api_v1_novels_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateNovelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateNovelResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_novel_api_v1_novels__novel_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NovelResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    apply_style_api_v1_novels__novel_id__applied_style_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApplyStyleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApplyStyleResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_chapters_api_v1_novels__novel_id__chapters_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_chapter_api_v1_novels__novel_id__chapters_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateChapterResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_characters_api_v1_novels__novel_id__characters_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_character_api_v1_novels__novel_id__characters_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCharacterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateCharacterResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_experiences_api_v1_novels__novel_id__characters__character_id__experiences_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                character_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExperienceResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_experience_api_v1_novels__novel_id__characters__character_id__experiences_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                character_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateExperienceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateExperienceResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_character_api_v1_novels__novel_id__characters__entity_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_character_api_v1_novels__novel_id__characters__entity_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateCharacterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_experience_api_v1_novels__novel_id__experiences__experience_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                experience_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_experience_api_v1_novels__novel_id__experiences__experience_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                experience_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateExperienceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExperienceResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_factions_api_v1_novels__novel_id__factions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FactionResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_faction_api_v1_novels__novel_id__factions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateFactionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateFactionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_faction_api_v1_novels__novel_id__factions__entity_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_faction_api_v1_novels__novel_id__factions__entity_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateFactionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FactionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_foreshadowings_api_v1_novels__novel_id__foreshadowings_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForeshadowingResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_foreshadowing_api_v1_novels__novel_id__foreshadowings_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateForeshadowingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForeshadowingResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_foreshadowing_api_v1_novels__novel_id__foreshadowings__foreshadowing_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                foreshadowing_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_foreshadowing_api_v1_novels__novel_id__foreshadowings__foreshadowing_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                foreshadowing_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateForeshadowingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForeshadowingResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_glossary_api_v1_novels__novel_id__glossary_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_glossary_api_v1_novels__novel_id__glossary_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateGlossaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateGlossaryResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_glossary_api_v1_novels__novel_id__glossary__entity_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_glossary_api_v1_novels__novel_id__glossary__entity_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateGlossaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_items_api_v1_novels__novel_id__items_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ItemResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_item_api_v1_novels__novel_id__items_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateItemRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateItemResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_item_api_v1_novels__novel_id__items__entity_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_item_api_v1_novels__novel_id__items__entity_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateItemRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ItemResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_locations_api_v1_novels__novel_id__locations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_location_api_v1_novels__novel_id__locations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateLocationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateLocationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_location_api_v1_novels__novel_id__locations__entity_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_location_api_v1_novels__novel_id__locations__entity_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                entity_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateLocationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LocationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_outline_api_v1_novels__novel_id__outline_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutlineContentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutlineContentResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_nodes_api_v1_novels__novel_id__outline_nodes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutlineNodeResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_node_api_v1_novels__novel_id__outline_nodes_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateOutlineNodeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutlineNodeMutationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_node_api_v1_novels__novel_id__outline_nodes__node_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                node_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteOutlineNodeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteOutlineNodeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_node_api_v1_novels__novel_id__outline_nodes__node_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                node_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateOutlineNodeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutlineNodeMutationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_plot_api_v1_novels__novel_id__plot_progress_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlotProgressRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlotProgressResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_references_api_v1_novels__novel_id__references_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReferenceMaterialResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_reference_api_v1_novels__novel_id__references_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateReferenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateReferenceResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_reference_api_v1_novels__novel_id__references__reference_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                reference_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteReferenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteReferenceImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_reference_api_v1_novels__novel_id__references__reference_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                reference_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateReferenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReferenceMaterialResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reindex_reference_api_v1_novels__novel_id__references__reference_id__reindex_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                reference_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReindexReferenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReindexAcceptedResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    search_references_api_v1_novels__novel_id__references_search_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RagSearchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RagSearchResult"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_relations_api_v1_novels__novel_id__relations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RelationResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_relation_api_v1_novels__novel_id__relations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateRelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateRelationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_relation_api_v1_novels__novel_id__relations__relation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                relation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeleteEntityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeleteImpactResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_relation_api_v1_novels__novel_id__relations__relation_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                relation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateRelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RelationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_story_background_api_v1_novels__novel_id__story_background_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_story_progress_api_v1_novels__novel_id__story_progress_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_novel_summary_api_v1_novels__novel_id__summary_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateNovelSummaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NovelResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_version_diff_api_v1_novels__novel_id__version_diff_get: {
        parameters: {
            query: {
                fromVersionId: string;
                toVersionId: string;
            };
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDiffResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_versions_api_v1_novels__novel_id__versions_get: {
        parameters: {
            query: {
                documentType: components["schemas"]["DocumentType"];
                chapterId?: string | null;
            };
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionListItem"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    submit_manual_version_api_v1_novels__novel_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ManualVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_version_api_v1_novels__novel_id__versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    adopt_candidate_version_api_v1_novels__novel_id__versions__version_id__adopt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    restore_historical_version_api_v1_novels__novel_id__versions__version_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_version_api_v1_novels__novel_id__versions_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionPreviewResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_api_v1_novels__novel_id__workspace_get: {
        parameters: {
            query?: {
                chapterId?: string | null;
            };
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_bootstrap_api_v1_novels__novel_id__workspace_bootstrap_get: {
        parameters: {
            query?: {
                chapterId?: string | null;
            };
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceBootstrapResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_lore_api_v1_novels__novel_id__workspace_lore_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceLoreResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_planning_api_v1_novels__novel_id__workspace_planning_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspacePlanningResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_workspace_resources_api_v1_novels__novel_id__workspace_resources_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResourcesResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_world_setting_api_v1_novels__novel_id__world_setting_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_writing_bible_api_v1_novels__novel_id__writing_bible_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WritingBibleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingBibleResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_portrait_task_api_v1_portrait_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortraitTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_quality_check_api_v1_quality_checks__check_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                check_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityCheckDto"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_quality_check_api_v1_quality_checks__check_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                check_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateQualityCheckRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualityCheckDto"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_quality_check_api_v1_quality_checks__check_id__run_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                check_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunQualityCheckRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunQualityCheckResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_review_artifact_summaries_api_v1_review_artifact_summaries_get: {
        parameters: {
            query: {
                novelId: string;
                chapterId?: string | null;
                taskId?: string | null;
                status?: string | null;
                kind?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewArtifactSummaryListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_review_artifacts_api_v1_review_artifacts_get: {
        parameters: {
            query: {
                novelId: string;
                chapterId?: string | null;
                taskId?: string | null;
                status?: string | null;
                kind?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewArtifactListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_review_artifact_api_v1_review_artifacts__artifact_id__get: {
        parameters: {
            query?: {
                revision?: number | null;
            };
            header?: {
                "If-None-Match"?: string | null;
            };
            path: {
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    /** @description artifactId、精确 revision 与权威状态共同生成的强 ETag */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewArtifactResponse"];
                };
            };
            /** @description 精确 revision 详情与 If-None-Match 一致 */
            304: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    decide_review_artifact_api_v1_review_artifacts__artifact_id__decision_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewArtifactDecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactDecisionPublicResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_styles_api_v1_styles_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StyleResponse"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_style_api_v1_styles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateStyleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StyleResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_style_api_v1_styles__style_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_portrait_api_v1_styles__style_id__portrait_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortraitAcceptedResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    upload_reference_api_v1_styles__style_id__references_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_reference_api_v1_styles__style_id__references_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StyleReferenceResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_reference_api_v1_styles__style_id__references__reference_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
                reference_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_section_api_v1_styles__style_id__sections__section__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
                section: "creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits";
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePortraitSectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StyleResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_section_portrait_api_v1_styles__style_id__sections__section__portrait_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                style_id: string;
                section: "creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits";
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortraitAcceptedResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    download_asset_api_v1_video_assets__asset_id__content_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": components["schemas"]["BinaryFileStream"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_asset_api_v1_video_assets__asset_id__preview_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": components["schemas"]["BinaryFileStream"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    confirm_asset_api_v1_video_assets__asset_id__rights_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfirmVideoAssetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoAssetResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_api_v1_video_episodes__episode_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_video_episode_api_v1_video_episodes__episode_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateVideoEpisodeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_command_api_v1_video_episodes__episode_id__commands__client_request_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                client_request_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeCommandResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_impact_reviews_api_v1_video_episodes__episode_id__impact_reviews_get: {
        parameters: {
            query?: {
                status?: ("pending" | "resolved") | null;
                limit?: number;
                beforeReviewId?: string | null;
            };
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoImpactReviewListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_impact_review_api_v1_video_episodes__episode_id__impact_reviews__review_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                review_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoImpactReviewResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    decide_video_impact_review_api_v1_video_episodes__episode_id__impact_reviews__review_id__decisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                review_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecideVideoImpactReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoImpactReviewResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_production_baselines_api_v1_video_episodes__episode_id__production_baselines_get: {
        parameters: {
            query?: {
                limit?: number;
                beforeVersionNo?: number | null;
            };
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProductionBaselineListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_production_baseline_api_v1_video_episodes__episode_id__production_baselines_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoProductionBaselineRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProductionBaselineResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_production_baseline_api_v1_video_episodes__episode_id__production_baselines__baseline_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProductionBaselineResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_episode_edit_versions_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions_get: {
        parameters: {
            query?: {
                limit?: number;
                beforeVersionNo?: number | null;
            };
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeEditVersionListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_episode_edit_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoEpisodeEditVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeEditVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_edit_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__edit_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeEditVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_video_episode_export_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartVideoEpisodeExportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeExportTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_export_task_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeExportTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    retry_video_episode_export_api_v1_video_episodes__episode_id__production_baselines__baseline_id__export_tasks__task_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryVideoEpisodeExportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeExportTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_delivery_api_v1_video_episodes__episode_id__production_baselines__baseline_id__exports__export_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                export_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeDeliveryResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_delivery_content_api_v1_video_episodes__episode_id__production_baselines__baseline_id__exports__export_id__content_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                export_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": components["schemas"]["BinaryFileStream"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_episode_mix_versions_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions_get: {
        parameters: {
            query?: {
                limit?: number;
                beforeVersionNo?: number | null;
            };
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeMixVersionListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_episode_mix_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoEpisodeMixVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeMixVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_mix_version_api_v1_video_episodes__episode_id__production_baselines__baseline_id__mix_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeMixVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_video_episode_shot_render_api_v1_video_episodes__episode_id__production_baselines__baseline_id__shots__shot_id__render_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                baseline_id: string;
                shot_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartVideoEpisodeShotRenderRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeRenderTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_render_task_api_v1_video_episodes__episode_id__render_tasks__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeRenderTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    retry_video_episode_render_task_api_v1_video_episodes__episode_id__render_tasks__task_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryVideoEpisodeShotRenderRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeRenderTaskResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    adopt_video_episode_script_candidate_api_v1_video_episodes__episode_id__script_candidates__artifact_id__adopt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdoptVideoEpisodeScriptCandidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    prepare_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrepareVideoEpisodeScriptConfirmationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptConfirmationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptConfirmationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    approve_video_episode_script_confirmation_api_v1_video_episodes__episode_id__script_confirmations__artifact_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveVideoEpisodeScriptConfirmationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_script_draft_api_v1_video_episodes__episode_id__script_draft_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_video_episode_script_draft_api_v1_video_episodes__episode_id__script_draft_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveVideoEpisodeScriptDraftRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_video_episode_script_run_api_v1_video_episodes__episode_id__script_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartVideoEpisodeScriptRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptRunResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_script_run_api_v1_video_episodes__episode_id__script_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                run_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptRunResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_episode_script_versions_api_v1_video_episodes__episode_id__script_versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptVersionListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_script_version_api_v1_video_episodes__episode_id__script_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeScriptVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_episode_source_sets_api_v1_video_episodes__episode_id__source_sets_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeSourceSetListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_episode_source_set_api_v1_video_episodes__episode_id__source_sets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoEpisodeSourceSetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeSourceSetResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_source_set_api_v1_video_episodes__episode_id__source_sets__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeSourceSetResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_storyboard_candidate_api_v1_video_episodes__episode_id__storyboard_candidates__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardCandidateResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    adopt_video_storyboard_candidate_api_v1_video_episodes__episode_id__storyboard_candidates__artifact_id__adopt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdoptVideoStoryboardCandidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    prepare_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrepareVideoStoryboardConfirmationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardConfirmationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardConfirmationResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    approve_video_storyboard_confirmation_api_v1_video_episodes__episode_id__storyboard_confirmations__artifact_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                artifact_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveVideoStoryboardConfirmationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_storyboard_draft_api_v1_video_episodes__episode_id__storyboard_draft_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    save_video_storyboard_draft_api_v1_video_episodes__episode_id__storyboard_draft_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveVideoStoryboardDraftRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardDraftResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_storyboard_runs_api_v1_video_episodes__episode_id__storyboard_runs_get: {
        parameters: {
            query?: {
                limit?: number;
                beforeRunId?: string | null;
            };
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardRunListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_video_storyboard_run_api_v1_video_episodes__episode_id__storyboard_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartVideoStoryboardRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardRunResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_storyboard_run_api_v1_video_episodes__episode_id__storyboard_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                run_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardRunResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_storyboard_versions_api_v1_video_episodes__episode_id__storyboard_versions_get: {
        parameters: {
            query?: {
                limit?: number;
                beforeVersionNo?: number | null;
            };
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardVersionListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_storyboard_version_api_v1_video_episodes__episode_id__storyboard_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                version_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoStoryboardVersionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_take_adoption_api_v1_video_episodes__episode_id__take_adoptions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoTakeAdoptionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoTakeAdoptionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_take_adoption_api_v1_video_episodes__episode_id__take_adoptions__adoption_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                adoption_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoTakeAdoptionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_take_candidates_api_v1_video_episodes__episode_id__takes_get: {
        parameters: {
            query: {
                targetShotVersionId: string;
                limit?: number;
                beforeTakeId?: string | null;
            };
            header?: never;
            path: {
                episode_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoTakeCandidateListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_episode_take_content_api_v1_video_episodes__episode_id__takes__take_id__content_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                episode_id: string;
                take_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": components["schemas"]["BinaryFileStream"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_projects_api_v1_video_novels__novel_id__projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProjectListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_project_api_v1_video_novels__novel_id__projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                novel_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProjectResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_production_capabilities_api_v1_video_production_capabilities_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProductionCapabilityResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_project_api_v1_video_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoProjectDetailResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    upload_asset_api_v1_video_projects__project_id__assets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_asset_api_v1_video_projects__project_id__assets_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoAssetResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_video_project_episode_command_api_v1_video_projects__project_id__episode_commands__client_request_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                client_request_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeCommandResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_video_episodes_api_v1_video_projects__project_id__episodes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_video_episode_api_v1_video_projects__project_id__episodes_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVideoEpisodeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    reorder_video_episodes_api_v1_video_projects__project_id__episodes_reorder_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReorderVideoEpisodesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VideoEpisodeListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_visual_canons_api_v1_video_projects__project_id__visual_canons_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VisualCanonLibraryResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    set_visual_canon_candidate_api_v1_video_projects__project_id__visual_canons_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateVisualCanonCandidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VisualCanonResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    approve_visual_canon_api_v1_video_visual_canons__canon_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                canon_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveVisualCanonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VisualCanonResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_writing_runs_api_v1_writing_runs_get: {
        parameters: {
            query: {
                novelId: string;
                chapterId?: string | null;
                writingSessionId?: string | null;
                operation?: string | null;
                outcome?: ("queued" | "running" | "waiting_user" | "succeeded" | "failed" | "cancelled" | "inconsistent") | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingRunListResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_writing_run_api_v1_writing_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartWritingRunRequest"] | components["schemas"]["ShortMediumStartWritingRunRequest"] | components["schemas"]["LongSerialStartWritingRunRequest"] | components["schemas"]["NaturalStartWritingRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingRunStartResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_writing_run_status_api_v1_writing_runs__task_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingRunStatusPublicResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    cancel_writing_run_api_v1_writing_runs__task_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelWritingRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelWritingRunPublicResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    clarify_writing_run_api_v1_writing_runs__task_id__clarification_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClarifyWritingRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingRunV2Response"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    stream_writing_run_events_api_v1_writing_runs__task_id__events_get: {
        parameters: {
            query?: never;
            header?: {
                "Last-Event-ID"?: string | null;
            };
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description 持续输出 V1 事件；V2 首帧为 RunSnapshot，后续为 WorkflowEventEnvelope。 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": components["schemas"]["WritingEventStream"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    resume_writing_run_api_v1_writing_runs__task_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeWritingRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResumeWritingRunResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_writing_sessions_api_v1_writing_sessions_get: {
        parameters: {
            query: {
                novelId: string;
                chapterId?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingSessionListItem"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_writing_session_api_v1_writing_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWritingSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingSessionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_writing_session_api_v1_writing_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingSessionDetail"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_writing_session_api_v1_writing_sessions__session_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_writing_session_api_v1_writing_sessions__session_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateWritingSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingSessionResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    add_writing_message_api_v1_writing_sessions__session_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_task_review_artifact_api_v1_writing_tasks__task_id__artifact_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewArtifactResponse"] | null;
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
