export interface paths {
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
    "/api/v1/video/projects/{project_id}/chapter-adaptations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Adaptations */
        get: operations["list_adaptations_api_v1_video_projects__project_id__chapter_adaptations_get"];
        put?: never;
        /** Create Adaptation */
        post: operations["create_adaptation_api_v1_video_projects__project_id__chapter_adaptations_post"];
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
    "/api/v1/video/chapter-adaptations/{adaptation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Adaptation */
        get: operations["get_adaptation_api_v1_video_chapter_adaptations__adaptation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Shot Plan */
        post: operations["start_shot_plan_api_v1_video_chapter_adaptations__adaptation_id__shot_plan_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Shot Plan */
        post: operations["confirm_shot_plan_api_v1_video_chapter_adaptations__adaptation_id__shot_plan_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/candidate/discard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Discard Candidate */
        post: operations["discard_candidate_api_v1_video_chapter_adaptations__adaptation_id__candidate_discard_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/episode-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Episode Plan */
        put: operations["save_episode_plan_api_v1_video_chapter_adaptations__adaptation_id__episode_plan_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/prompt-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Prompt Run */
        post: operations["start_prompt_run_api_v1_video_chapter_adaptations__adaptation_id__prompt_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/prompt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Shot Prompt */
        put: operations["save_shot_prompt_api_v1_video_chapter_adaptations__adaptation_id__shots__shot_id__prompt_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/visual-references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Shot Visual References */
        put: operations["save_shot_visual_references_api_v1_video_chapter_adaptations__adaptation_id__shots__shot_id__visual_references_put"];
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
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AbsenceSentinel */
        AbsenceSentinel: {
            /** Resourcetype */
            resourceType: string;
            /** Resourceid */
            resourceId: string;
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
            /** Styleid */
            styleId: string | null;
            /** Expectedstyleid */
            expectedStyleId: string | null;
        };
        /** ApplyStyleResponse */
        ApplyStyleResponse: {
            /** Styleid */
            styleId: string | null;
            /** Effective */
            effective: boolean;
        };
        /** ApproveVisualCanonRequest */
        ApproveVisualCanonRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Candidateassetid */
            candidateAssetId: string;
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
            /** Taskid */
            taskId: string;
            /** Commandid */
            commandId: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "discard" | "revise";
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /**
             * Savedcount
             * @default 0
             */
            savedCount: number;
            /**
             * Deleted
             * @default false
             */
            deleted: boolean;
        };
        /** ArtifactEvaluationResponse */
        ArtifactEvaluationResponse: {
            /** Id */
            id: string;
            /** Artifactid */
            artifactId: string;
            /** Revision */
            revision: number;
            /** Evaluatoragent */
            evaluatorAgent: string;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "pass" | "revise" | "block";
            /** Summary */
            summary: string;
            /** Requiredchanges */
            requiredChanges: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** ArtifactSelectionRef */
        ArtifactSelectionRef: {
            /** Section */
            section: string;
            /** Index */
            index?: number | null;
        };
        /**
         * BeatCoverageGoal
         * @description 一个节拍希望观众获得的内容，不预设必须使用哪类镜头完成。
         */
        BeatCoverageGoal: {
            /** Goalkey */
            goalKey: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "story_information" | "action" | "emotion" | "space" | "relationship" | "motif" | "transition";
            /**
             * Priority
             * @enum {string}
             */
            priority: "essential" | "supporting";
            /** Description */
            description: string;
        };
        /** BeatPlanDto */
        BeatPlanDto: {
            /** Id */
            id: string;
            /** Chapterid */
            chapterId: string;
            /** Goalid */
            goalId: string | null;
            status: components["schemas"]["BeatPlanStatus"];
            /** Chaptergoal */
            chapterGoal: string;
            /** Mainplotconnection */
            mainPlotConnection: string | null;
            /** Chapteracceptancecriteria */
            chapterAcceptanceCriteria: string | null;
            /** Totalestimatedwords */
            totalEstimatedWords: number;
            /** Generatedby */
            generatedBy: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Scenebeats */
            sceneBeats: components["schemas"]["SceneBeatDto"][];
        };
        /** @enum {string} */
        BeatPlanStatus: "draft" | "reviewing" | "approved" | "rejected" | "superseded";
        /** BillingSummaryResponse */
        BillingSummaryResponse: {
            /** Username */
            username: string;
            /** Balancemicros */
            balanceMicros: string;
            /** Balancecredits */
            balanceCredits: string;
            /** Recentledger */
            recentLedger: components["schemas"]["LedgerEntryResponse"][];
        };
        /** BillingUsageResponse */
        BillingUsageResponse: {
            totalUsage: components["schemas"]["TokenUsageBreakdown"];
            monthlyUsage: components["schemas"]["TokenUsageBreakdown"];
        };
        /** Body_upload_asset_api_v1_video_projects__project_id__assets_post */
        Body_upload_asset_api_v1_video_projects__project_id__assets_post: {
            /** File */
            file: string;
            /** Name */
            name: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "image" | "video" | "audio";
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "music";
            /**
             * Sourcekind
             * @default user_upload
             * @enum {string}
             */
            sourceKind: "user_upload" | "authorized_real" | "virtual" | "model_generated";
        };
        /** Body_upload_reference_api_v1_styles__style_id__references_post */
        Body_upload_reference_api_v1_styles__style_id__references_post: {
            /** File */
            file: string;
        };
        /** CancelWritingRunRequest */
        CancelWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CancelWritingRunResponse */
        CancelWritingRunResponse: {
            /** Taskid */
            taskId: string;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /** Effective */
            effective: boolean;
            /** Alreadyterminal */
            alreadyTerminal: boolean;
            /** Cancelledcommandid */
            cancelledCommandId: string | null;
            /** Cancelledjobid */
            cancelledJobId: string | null;
        };
        /** ChapterAdaptationListResponse */
        ChapterAdaptationListResponse: {
            /** Adaptations */
            adaptations: components["schemas"]["ChapterAdaptationResponse"][];
        };
        /**
         * ChapterAdaptationPlanCandidate
         * @description 进入 ReviewArtifact 的完整 Scene → Beat → Shot 候选。
         */
        ChapterAdaptationPlanCandidate: {
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "chapter_adaptation_plan_v3";
            /** Adaptationid */
            adaptationId: string;
            /** Sourcehash */
            sourceHash: string;
            /** Scenes */
            scenes: components["schemas"]["CinematicSceneCandidate"][];
            /** Suggestedepisodebreakaftershotkeys */
            suggestedEpisodeBreakAfterShotKeys?: string[];
            /** Reviewsummary */
            reviewSummary?: string | null;
            /** Reviewfindings */
            reviewFindings?: components["schemas"]["CinematicReviewFinding"][];
        };
        /** ChapterAdaptationResponse */
        ChapterAdaptationResponse: {
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Chaptertitle */
            chapterTitle: string;
            /**
             * Chapterupdatedat
             * Format: date-time
             */
            chapterUpdatedAt: string;
            /** Sourcetext */
            sourceText: string;
            /** Sourcehash */
            sourceHash: string;
            /** Lifecyclestatus */
            lifecycleStatus: string;
            /** Headrevision */
            headRevision: number;
            /**
             * State
             * @enum {string}
             */
            state: "empty" | "generating" | "awaiting_review" | "approved" | "failed";
            currentPlan: components["schemas"]["FormalChapterAdaptationPlan"] | null;
            candidatePlan: components["schemas"]["ChapterAdaptationPlanCandidate"] | null;
            episodePlan: components["schemas"]["EpisodePlanResponse"] | null;
            /** Promptversions */
            promptVersions: components["schemas"]["ShotPromptVersionResponse"][];
            /** Promptcandidates */
            promptCandidates: components["schemas"]["ShotPromptCandidateResponse"][];
            /** Visualreferencesets */
            visualReferenceSets: components["schemas"]["ShotVisualReferenceSetResponse"][];
            reviewArtifact: components["schemas"]["ChapterAdaptationReviewSummary"] | null;
            latestTask: components["schemas"]["ChapterAdaptationTaskResponse"] | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** ChapterAdaptationReviewSummary */
        ChapterAdaptationReviewSummary: {
            /** Id */
            id: string;
            /** Status */
            status: string;
            /** Revision */
            revision: number;
            /** Title */
            title: string | null;
            /** Summary */
            summary: string | null;
        };
        /**
         * ChapterAdaptationSourceRange
         * @description 相对于不可变章节全文的 Unicode code point 左闭右开范围。
         */
        ChapterAdaptationSourceRange: {
            /** Start */
            start: number;
            /** End */
            end: number;
            /** Sourcetext */
            sourceText: string;
        };
        /** ChapterAdaptationTaskAcceptedResponse */
        ChapterAdaptationTaskAcceptedResponse: {
            adaptation: components["schemas"]["ChapterAdaptationResponse"];
            task: components["schemas"]["ChapterAdaptationTaskResponse"];
        };
        /** ChapterAdaptationTaskResponse */
        ChapterAdaptationTaskResponse: {
            /** Id */
            id: string;
            /** Jobid */
            jobId: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "shot_plan" | "shot_prompt";
            /** Baseshotplanversionid */
            baseShotPlanVersionId: string | null;
            /** Workflow */
            workflow: string;
            /** Status */
            status: string;
            /** Checkpointstage */
            checkpointStage: string;
            /** Lasterrorcode */
            lastErrorCode: string | null;
            /** Lasterrormessage */
            lastErrorMessage: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
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
            /** Id */
            id: string;
            /** Chapterid */
            chapterId: string;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Expectedupdatedat */
            expectedUpdatedAt: string | null;
        };
        /** ChapterRangeScope */
        ChapterRangeScope: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "chapter_range";
            /** Chapterstartorder */
            chapterStartOrder: number;
            /** Chapterendorder */
            chapterEndOrder: number;
        };
        /** ChapterScope */
        ChapterScope: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "chapter";
            /** Chapterid */
            chapterId: string;
        };
        /** @enum {string} */
        ChapterStatus: "drafting" | "review" | "completed";
        /** ChapterStatusRequest */
        ChapterStatusRequest: {
            status: components["schemas"]["ChapterStatus"];
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** ChapterStatusResponse */
        ChapterStatusResponse: {
            /** Id */
            id: string;
            status: components["schemas"]["ChapterStatus"];
            /** Completedat */
            completedAt: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ChapterTarget */
        ChapterTarget: {
            /**
             * Type
             * @constant
             */
            type: "chapter";
            /** Id */
            id: string;
        };
        /** CharacterDto */
        CharacterDto: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Aliases */
            aliases: string | null;
            /** Gender */
            gender: string | null;
            /** Age */
            age: string | null;
            /** Appearance */
            appearance: string | null;
            /** Personality */
            personality: string | null;
            /** Identity */
            identity: string | null;
            /** Background */
            background: string | null;
            /** Coredesire */
            coreDesire: string | null;
            /** Behaviorboundaries */
            behaviorBoundaries: string | null;
            /** Speechstyle */
            speechStyle: string | null;
            /** Relationshipprinciples */
            relationshipPrinciples: string | null;
            /** Shorttermgoal */
            shortTermGoal: string | null;
            /** Factionid */
            factionId: string | null;
            faction: components["schemas"]["FactionSummary"] | null;
            /** Powerlevel */
            powerLevel: string | null;
            /** Combatability */
            combatAbility: string | null;
            /** Specialskills */
            specialSkills: string | null;
            currentStatus: components["schemas"]["CharacterStatus"];
            /** Statusnote */
            statusNote: string | null;
            /** Experiences */
            experiences: components["schemas"]["CharacterExperienceDto"][];
            /** Outgoingrelations */
            outgoingRelations: components["schemas"]["CharacterRelationDto"][];
            /** Incomingrelations */
            incomingRelations: components["schemas"]["CharacterRelationDto"][];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterExperienceDto */
        CharacterExperienceDto: {
            /** Id */
            id: string;
            /** Chapterid */
            chapterId: string | null;
            /** Content */
            content: string;
            /** Order */
            order: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterRelationDto */
        CharacterRelationDto: {
            /** Id */
            id: string;
            /** Characterid */
            characterId: string;
            /** Targetid */
            targetId: string;
            relationType: components["schemas"]["RelationType"];
            /** Intimacy */
            intimacy: number;
            /** Description */
            description: string | null;
            /** Startdate */
            startDate: string | null;
            /** Enddate */
            endDate: string | null;
            character?: components["schemas"]["RelationPeer"] | null;
            target?: components["schemas"]["RelationPeer"] | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** CharacterResponse */
        CharacterResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Gender */
            gender?: string | null;
            /** Age */
            age?: string | null;
            /** Appearance */
            appearance?: string | null;
            /** Personality */
            personality?: string | null;
            /** Identity */
            identity?: string | null;
            /** Background */
            background?: string | null;
            /** Coredesire */
            coreDesire?: string | null;
            /** Behaviorboundaries */
            behaviorBoundaries?: string | null;
            /** Speechstyle */
            speechStyle?: string | null;
            /** Relationshipprinciples */
            relationshipPrinciples?: string | null;
            /** Shorttermgoal */
            shortTermGoal?: string | null;
            /** Factionid */
            factionId?: string | null;
            /** Powerlevel */
            powerLevel?: string | null;
            /** Combatability */
            combatAbility?: string | null;
            /** Specialskills */
            specialSkills?: string | null;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            /** Statusnote */
            statusNote?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        CharacterStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
        /**
         * CinematicReviewFinding
         * @description 面向作者的非阻断审镜发现。
         */
        CinematicReviewFinding: {
            /**
             * Severity
             * @enum {string}
             */
            severity: "notice" | "warning";
            /**
             * Scope
             * @enum {string}
             */
            scope: "plan" | "scene" | "beat" | "shot";
            /** Scopekey */
            scopeKey?: string | null;
            /** Message */
            message: string;
            /** Evidence */
            evidence: string;
            /** Suggestion */
            suggestion: string;
        };
        /**
         * CinematicSceneCandidate
         * @description 由时间、地点和连续行动空间决定的真实场景候选。
         */
        CinematicSceneCandidate: {
            /** Scenekey */
            sceneKey: string;
            /** Title */
            title: string;
            /** Locationlabel */
            locationLabel: string;
            /** Timelabel */
            timeLabel: string;
            /** Objective */
            objective: string;
            /** Changesummary */
            changeSummary: string;
            /** Beats */
            beats: components["schemas"]["DramaticBeatCandidate"][];
        };
        /**
         * CinematicShotCandidate
         * @description 候选镜头是一段连续机位和一个主要可见动作。
         */
        CinematicShotCandidate: {
            /** Shotkey */
            shotKey: string;
            /** Title */
            title: string;
            /**
             * Narrativepurpose
             * @enum {string}
             */
            narrativePurpose: "establishing" | "action" | "dialogue" | "reaction" | "reveal" | "insert" | "transition" | "atmosphere";
            /** Storyfunction */
            storyFunction: string;
            /** Audiencegain */
            audienceGain: string;
            /** Coveredgoalkeys */
            coveredGoalKeys?: string[];
            /**
             * Sourcerelation
             * @enum {string}
             */
            sourceRelation: "direct" | "derived" | "supplemental";
            /**
             * Shotscale
             * @enum {string}
             */
            shotScale: "extreme_long" | "long" | "medium" | "medium_close" | "close" | "extreme_close" | "over_shoulder" | "two_shot" | "pov";
            /**
             * Cameraangle
             * @enum {string}
             */
            cameraAngle: "eye_level" | "high_angle" | "low_angle" | "overhead" | "dutch_angle";
            /**
             * Cameramovement
             * @enum {string}
             */
            cameraMovement: "locked" | "pan" | "tilt" | "push_in" | "pull_out" | "tracking" | "arc" | "handheld" | "focus_shift";
            /** Visualintent */
            visualIntent: string;
            /**
             * Speechmode
             * @enum {string}
             */
            speechMode: "none" | "sync" | "offscreen" | "voiceover";
            /** Spokentext */
            spokenText?: string | null;
            /** Sounddesign */
            soundDesign: string;
            /** Cutreason */
            cutReason: string;
            /** Timelinedurationms */
            timelineDurationMs: number;
            /** Sourceranges */
            sourceRanges: components["schemas"]["ChapterAdaptationSourceRange"][];
        };
        /** ConfirmAdaptationPlanRequest */
        ConfirmAdaptationPlanRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expectedadaptationrevision */
            expectedAdaptationRevision: number;
            plan: components["schemas"]["ChapterAdaptationPlanCandidate"];
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
            /** Id */
            id: string;
            /** Content */
            content: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ContentRequest */
        ContentRequest: {
            /** Content */
            content: string | null;
            /** Expectedupdatedat */
            expectedUpdatedAt: string | null;
        };
        /** ContentResponse */
        ContentResponse: {
            /** Id */
            id: string;
            /** Content */
            content: string | null;
            /** Createdat */
            createdAt?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** CreateChapterAdaptationRequest */
        CreateChapterAdaptationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Chapterid */
            chapterId: string;
            /**
             * Expectedchapterupdatedat
             * Format: date-time
             */
            expectedChapterUpdatedAt: string;
        };
        /** CreateChapterResponse */
        CreateChapterResponse: {
            chapter: components["schemas"]["WorkspaceChapter"];
        };
        /** CreateCharacterRequest */
        CreateCharacterRequest: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Gender */
            gender?: string | null;
            /** Age */
            age?: string | null;
            /** Appearance */
            appearance?: string | null;
            /** Personality */
            personality?: string | null;
            /** Identity */
            identity?: string | null;
            /** Background */
            background?: string | null;
            /** Coredesire */
            coreDesire?: string | null;
            /** Behaviorboundaries */
            behaviorBoundaries?: string | null;
            /** Speechstyle */
            speechStyle?: string | null;
            /** Relationshipprinciples */
            relationshipPrinciples?: string | null;
            /** Shorttermgoal */
            shortTermGoal?: string | null;
            /** Factionid */
            factionId?: string | null;
            /** Powerlevel */
            powerLevel?: string | null;
            /** Combatability */
            combatAbility?: string | null;
            /** Specialskills */
            specialSkills?: string | null;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            /** Statusnote */
            statusNote?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateCharacterResponse */
        CreateCharacterResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Gender */
            gender?: string | null;
            /** Age */
            age?: string | null;
            /** Appearance */
            appearance?: string | null;
            /** Personality */
            personality?: string | null;
            /** Identity */
            identity?: string | null;
            /** Background */
            background?: string | null;
            /** Coredesire */
            coreDesire?: string | null;
            /** Behaviorboundaries */
            behaviorBoundaries?: string | null;
            /** Speechstyle */
            speechStyle?: string | null;
            /** Relationshipprinciples */
            relationshipPrinciples?: string | null;
            /** Shorttermgoal */
            shortTermGoal?: string | null;
            /** Factionid */
            factionId?: string | null;
            /** Powerlevel */
            powerLevel?: string | null;
            /** Combatability */
            combatAbility?: string | null;
            /** Specialskills */
            specialSkills?: string | null;
            /**
             * Currentstatus
             * @default active
             * @enum {string}
             */
            currentStatus: "active" | "missing" | "dead" | "imprisoned" | "unknown";
            /** Statusnote */
            statusNote?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateExperienceRequest */
        CreateExperienceRequest: {
            /** Chapterid */
            chapterId?: string | null;
            /** Content */
            content: string;
            /** Order */
            order?: number | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateExperienceResponse */
        CreateExperienceResponse: {
            /** Id */
            id: string;
            /** Characterid */
            characterId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Content */
            content: string;
            /** Order */
            order: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateFactionRequest */
        CreateFactionRequest: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Baseid */
            baseId?: string | null;
            /** Description */
            description?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateFactionResponse */
        CreateFactionResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Baseid */
            baseId?: string | null;
            /** Description */
            description?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateForeshadowingRequest */
        CreateForeshadowingRequest: {
            /** Name */
            name: string;
            /** Plantedat */
            plantedAt?: string | null;
            /** Plantedcontent */
            plantedContent?: string | null;
            /** Expectedpayoff */
            expectedPayoff?: string | null;
            /** Payoffat */
            payoffAt?: string | null;
            /**
             * Status
             * @default active
             * @enum {string}
             */
            status: "active" | "paid_off" | "abandoned";
        };
        /** CreateGlossaryRequest */
        CreateGlossaryRequest: {
            /** Term */
            term: string;
            /** Definition */
            definition: string;
            /** Category */
            category?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateGlossaryResponse */
        CreateGlossaryResponse: {
            /** Term */
            term: string;
            /** Definition */
            definition: string;
            /** Category */
            category?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateItemRequest */
        CreateItemRequest: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Rarity */
            rarity?: string | null;
            /** Effect */
            effect?: string | null;
            /** Origin */
            origin?: string | null;
            /** Description */
            description?: string | null;
            /** Ownerid */
            ownerId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateItemResponse */
        CreateItemResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Rarity */
            rarity?: string | null;
            /** Effect */
            effect?: string | null;
            /** Origin */
            origin?: string | null;
            /** Description */
            description?: string | null;
            /** Ownerid */
            ownerId?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateLocationRequest */
        CreateLocationRequest: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Parentid */
            parentId?: string | null;
            /** Climate */
            climate?: string | null;
            /** Culture */
            culture?: string | null;
            /** Description */
            description?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateLocationResponse */
        CreateLocationResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Parentid */
            parentId?: string | null;
            /** Climate */
            climate?: string | null;
            /** Culture */
            culture?: string | null;
            /** Description */
            description?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateMessageRequest */
        CreateMessageRequest: {
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "agent" | "system";
            /** Agentid */
            agentId?: string | null;
            /** Content */
            content: string;
            /** Intent */
            intent?: string | null;
            metadata?: components["schemas"]["JsonValue"] | null;
            /** Parentid */
            parentId?: string | null;
        };
        /** CreateNovelRequest */
        CreateNovelRequest: {
            /** Name */
            name: string;
            /** Summary */
            summary?: string | null;
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
            /** Clientrequestid */
            clientRequestId?: string | null;
            sourceKind?: components["schemas"]["ShortMediumSourceKind"] | null;
            /** Sourcetext */
            sourceText?: string | null;
            /** Genre */
            genre?: string | null;
            /** Protagonist */
            protagonist?: string | null;
            /** Coresellingpoint */
            coreSellingPoint?: string | null;
            /** Readerpromise */
            readerPromise?: string | null;
            /** Firstchaptergoal */
            firstChapterGoal?: string | null;
        };
        /** CreateNovelResponse */
        CreateNovelResponse: {
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
        };
        /** CreateOutlineNodeRequest */
        CreateOutlineNodeRequest: {
            /** Title */
            title: string;
            /** Content */
            content?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /**
             * Order
             * @default 0
             */
            order: number;
            /** Parentid */
            parentId?: string | null;
            /** Linkedchapterid */
            linkedChapterId?: string | null;
            /** Estimatedwordcount */
            estimatedWordCount?: number | null;
            /** Actualwordcount */
            actualWordCount?: number | null;
            /** Chapterstartorder */
            chapterStartOrder?: number | null;
            /** Chapterendorder */
            chapterEndOrder?: number | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateReferenceRequest */
        CreateReferenceRequest: {
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
            /** Content */
            content: string;
            /** Sourceurl */
            sourceUrl?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateReferenceResponse */
        CreateReferenceResponse: {
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
            /** Content */
            content: string;
            /** Sourceurl */
            sourceUrl?: string | null;
            /** Id */
            id: string;
            /**
             * Ragstatus
             * @enum {string}
             */
            ragStatus: "disabled" | "ready" | "failed";
            /** Contenthash */
            contentHash: string;
            /** Errormessage */
            errorMessage: string | null;
            /** Createdat */
            createdAt?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
            /** Effective */
            effective: boolean;
        };
        /** CreateRelationRequest */
        CreateRelationRequest: {
            /** Characterid */
            characterId: string;
            /** Targetid */
            targetId: string;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /** Description */
            description?: string | null;
            /** Startdate */
            startDate?: string | null;
            /** Enddate */
            endDate?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CreateRelationResponse */
        CreateRelationResponse: {
            /** Characterid */
            characterId: string;
            /** Targetid */
            targetId: string;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /** Description */
            description?: string | null;
            /** Startdate */
            startDate?: string | null;
            /** Enddate */
            endDate?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** CreateStyleRequest */
        CreateStyleRequest: {
            /** Name */
            name: string;
        };
        /**
         * CreateVideoProjectRequest
         * @description 创建一个独立于写作任务的视频项目。
         */
        CreateVideoProjectRequest: {
            /** Title */
            title: string;
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
        };
        /**
         * CreateVisualCanonCandidateRequest
         * @description 把已上传且已确认权利的图片放入一个视觉设定槽的候选位置。
         */
        CreateVisualCanonCandidateRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Settingkind
             * @enum {string}
             */
            settingKind: "character" | "location" | "item";
            /** Settingid */
            settingId: string;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Variantkey */
            variantKey: string;
            /** Label */
            label: string;
            /** Candidateassetid */
            candidateAssetId: string;
            /** Includefeatures */
            includeFeatures?: string[];
            /** Excludefeatures */
            excludeFeatures?: string[];
            /**
             * Defaultstrength
             * @default 70
             */
            defaultStrength: number;
        };
        /** CreateWritingSessionRequest */
        CreateWritingSessionRequest: {
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Title */
            title?: string | null;
        };
        /** DashboardNovel */
        DashboardNovel: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Summary */
            summary: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Chapters */
            chapters: components["schemas"]["ChapterIdSummary"][];
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
        };
        /** DashboardResponse */
        DashboardResponse: {
            /** Novels */
            novels: components["schemas"]["DashboardNovel"][];
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
            /**
             * Deletedtype
             * @enum {string}
             */
            deletedType: "characters" | "items" | "locations" | "factions" | "glossary" | "experience" | "relation";
            /** Deletedid */
            deletedId: string;
            /** Affected */
            affected: {
                [key: string]: number;
            };
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
            /**
             * Reference
             * @constant
             */
            reference: 1;
            /**
             * Ragdocuments
             * @enum {integer}
             */
            ragDocuments: 0 | 1;
            /** Ragchunks */
            ragChunks: number;
        };
        /** DeleteReferenceImpactResponse */
        DeleteReferenceImpactResponse: {
            /**
             * Deletedtype
             * @constant
             */
            deletedType: "reference";
            /** Deletedid */
            deletedId: string;
            affected: components["schemas"]["DeleteReferenceAffected"];
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
            /**
             * Type
             * @enum {string}
             */
            type: "insert" | "delete" | "replace";
            /** Oldstart */
            oldStart: number;
            /** Oldend */
            oldEnd: number;
            /** Newstart */
            newStart: number;
            /** Newend */
            newEnd: number;
            /** Oldtext */
            oldText?: string | null;
            /** Newtext */
            newText?: string | null;
        };
        /** DiscardAdaptationCandidateRequest */
        DiscardAdaptationCandidateRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expectedadaptationrevision */
            expectedAdaptationRevision: number;
        };
        /** @enum {string} */
        DocumentType: "outline" | "manuscript";
        /** DocumentVersionPayload */
        DocumentVersionPayload: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "outline_draft" | "chapter_draft";
            documentType: components["schemas"]["DocumentType"];
            /** Versionnumber */
            versionNumber: number;
            /** Baseversionid */
            baseVersionId?: string | null;
            /** Clientrequestid */
            clientRequestId?: string | null;
            source: components["schemas"]["VersionSource"];
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /** Sourcetaskid */
            sourceTaskId?: string | null;
            /** Sourcejobid */
            sourceJobId?: string | null;
            /** Sourceoutlineversionid */
            sourceOutlineVersionId?: string | null;
            /** Userinstruction */
            userInstruction?: string | null;
            /** Sourcekind */
            sourceKind?: ("idea" | "opening" | "ending" | "outline" | "mixed") | null;
            /** Sourcetext */
            sourceText?: string | null;
            /** Restoredfromversionid */
            restoredFromVersionId?: string | null;
            /**
             * Createdfromselection
             * @default false
             */
            createdFromSelection: boolean;
            /** Selectionstart */
            selectionStart?: number | null;
            /** Selectionend */
            selectionEnd?: number | null;
            /** Selectedtexthash */
            selectedTextHash?: string | null;
        };
        /**
         * DramaticBeatCandidate
         * @description 戏剧节拍表达人物目标、信息、情绪、权力或行动结果的变化。
         */
        DramaticBeatCandidate: {
            /** Beatkey */
            beatKey: string;
            /** Title */
            title: string;
            /** Dramaticturn */
            dramaticTurn: string;
            /** Visualstrategy */
            visualStrategy: string;
            /** Coveragegoals */
            coverageGoals: components["schemas"]["BeatCoverageGoal"][];
            /** Sourceranges */
            sourceRanges: components["schemas"]["ChapterAdaptationSourceRange"][];
            /** Shots */
            shots: components["schemas"]["CinematicShotCandidate"][];
        };
        /** EpisodePlanResponse */
        EpisodePlanResponse: {
            /** Id */
            id: string;
            /** Versionno */
            versionNo: number;
            /** Shotplanversionid */
            shotPlanVersionId: string;
            /** Breakaftershotids */
            breakAfterShotIds: string[];
        };
        /** ErrorResponse */
        ErrorResponse: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            details: components["schemas"]["JsonValue"] | null;
            /** Requestid */
            requestId: string;
        };
        /** ExperienceResponse */
        ExperienceResponse: {
            /** Id */
            id: string;
            /** Characterid */
            characterId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Content */
            content: string;
            /** Order */
            order: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FactionDto */
        FactionDto: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Aliases */
            aliases: string | null;
            /** Type */
            type: string | null;
            /** Baseid */
            baseId: string | null;
            /** Description */
            description: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FactionResponse */
        FactionResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Baseid */
            baseId?: string | null;
            /** Description */
            description?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Name */
            name: string;
            /** Plantedat */
            plantedAt?: string | null;
            /** Plantedcontent */
            plantedContent?: string | null;
            /** Expectedpayoff */
            expectedPayoff?: string | null;
            /** Payoffat */
            payoffAt?: string | null;
            /**
             * Status
             * @default active
             * @enum {string}
             */
            status: "active" | "paid_off" | "abandoned";
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** FormalChapterAdaptationPlan */
        FormalChapterAdaptationPlan: {
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "chapter_adaptation_plan_v3";
            /** Planversionid */
            planVersionId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId?: string | null;
            /** Adaptationid */
            adaptationId: string;
            /** Sourcehash */
            sourceHash: string;
            /** Scenes */
            scenes: components["schemas"]["FormalCinematicScene"][];
            /** Episodebreakaftershotkeys */
            episodeBreakAfterShotKeys?: string[];
        };
        /** FormalCinematicScene */
        FormalCinematicScene: {
            /** Id */
            id: string;
            /** Scenekey */
            sceneKey: string;
            /** Title */
            title: string;
            /** Locationlabel */
            locationLabel: string;
            /** Timelabel */
            timeLabel: string;
            /** Objective */
            objective: string;
            /** Changesummary */
            changeSummary: string;
            /** Beats */
            beats: components["schemas"]["FormalDramaticBeat"][];
        };
        /**
         * FormalCinematicShot
         * @description 批准后具有数据库身份的正式镜头读模型。
         */
        FormalCinematicShot: {
            /** Shotkey */
            shotKey: string;
            /** Title */
            title: string;
            /**
             * Narrativepurpose
             * @enum {string}
             */
            narrativePurpose: "establishing" | "action" | "dialogue" | "reaction" | "reveal" | "insert" | "transition" | "atmosphere";
            /** Storyfunction */
            storyFunction: string;
            /** Audiencegain */
            audienceGain: string;
            /** Coveredgoalkeys */
            coveredGoalKeys?: string[];
            /**
             * Sourcerelation
             * @enum {string}
             */
            sourceRelation: "direct" | "derived" | "supplemental";
            /**
             * Shotscale
             * @enum {string}
             */
            shotScale: "extreme_long" | "long" | "medium" | "medium_close" | "close" | "extreme_close" | "over_shoulder" | "two_shot" | "pov";
            /**
             * Cameraangle
             * @enum {string}
             */
            cameraAngle: "eye_level" | "high_angle" | "low_angle" | "overhead" | "dutch_angle";
            /**
             * Cameramovement
             * @enum {string}
             */
            cameraMovement: "locked" | "pan" | "tilt" | "push_in" | "pull_out" | "tracking" | "arc" | "handheld" | "focus_shift";
            /** Visualintent */
            visualIntent: string;
            /**
             * Speechmode
             * @enum {string}
             */
            speechMode: "none" | "sync" | "offscreen" | "voiceover";
            /** Spokentext */
            spokenText?: string | null;
            /** Sounddesign */
            soundDesign: string;
            /** Cutreason */
            cutReason: string;
            /** Timelinedurationms */
            timelineDurationMs: number;
            /** Sourceranges */
            sourceRanges: components["schemas"]["ChapterAdaptationSourceRange"][];
            /** Id */
            id: string;
        };
        /** FormalDramaticBeat */
        FormalDramaticBeat: {
            /** Id */
            id: string;
            /** Beatkey */
            beatKey: string;
            /** Title */
            title: string;
            /** Dramaticturn */
            dramaticTurn: string;
            /** Visualstrategy */
            visualStrategy: string;
            /** Coveragegoals */
            coverageGoals: components["schemas"]["BeatCoverageGoal"][];
            /** Sourceranges */
            sourceRanges: components["schemas"]["ChapterAdaptationSourceRange"][];
            /** Shots */
            shots: components["schemas"]["FormalCinematicShot"][];
        };
        /** GlossaryDto */
        GlossaryDto: {
            /** Id */
            id: string;
            /** Term */
            term: string;
            /** Definition */
            definition: string;
            /** Category */
            category: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** GlossaryResponse */
        GlossaryResponse: {
            /** Term */
            term: string;
            /** Definition */
            definition: string;
            /** Category */
            category?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ItemDto */
        ItemDto: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Aliases */
            aliases: string | null;
            /** Type */
            type: string | null;
            /** Rarity */
            rarity: string | null;
            /** Effect */
            effect: string | null;
            /** Origin */
            origin: string | null;
            /** Description */
            description: string | null;
            /** Ownerid */
            ownerId: string | null;
            owner: components["schemas"]["OwnerSummary"] | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ItemResponse */
        ItemResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Rarity */
            rarity?: string | null;
            /** Effect */
            effect?: string | null;
            /** Origin */
            origin?: string | null;
            /** Description */
            description?: string | null;
            /** Ownerid */
            ownerId?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        JsonValue: unknown;
        /** LastMessageResponse */
        LastMessageResponse: {
            /** Content */
            content: string;
            /** Role */
            role: string;
            /** Agentid */
            agentId: string | null;
        };
        /** LedgerEntryResponse */
        LedgerEntryResponse: {
            /** Id */
            id: string;
            /** Type */
            type: string;
            /** Amountmicros */
            amountMicros: string;
            /** Balanceaftermicros */
            balanceAfterMicros: string;
            /** Note */
            note: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** LiveHealthResponse */
        LiveHealthResponse: {
            /**
             * Status
             * @constant
             */
            status: "ok";
            /**
             * Service
             * @constant
             */
            service: "core-api";
        };
        /** LocationDto */
        LocationDto: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Aliases */
            aliases: string | null;
            /** Type */
            type: string | null;
            /** Parentid */
            parentId: string | null;
            /** Climate */
            climate: string | null;
            /** Culture */
            culture: string | null;
            /** Description */
            description: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** LocationResponse */
        LocationResponse: {
            /** Name */
            name: string;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Parentid */
            parentId?: string | null;
            /** Climate */
            climate?: string | null;
            /** Culture */
            culture?: string | null;
            /** Description */
            description?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /** Username */
            username: string;
            /**
             * Password
             * Format: password
             */
            password: string;
        };
        /** LongSerialStartWritingRunRequest */
        LongSerialStartWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Workflow
             * @constant
             */
            workflow: "long_serial";
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId?: string | null;
            /**
             * Operation
             * @enum {string}
             */
            operation: "answer_question" | "create_lore" | "revise_lore" | "create_outline" | "revise_outline" | "plan_chapter" | "write_chapter" | "rewrite_scene" | "rewrite_chapter_selection" | "rewrite_outline_selection" | "review_chapter" | "manage_foreshadowing";
            target: components["schemas"]["ChapterTarget"];
            /** Scope */
            scope: components["schemas"]["ChapterScope"] | components["schemas"]["ChapterRangeScope"] | components["schemas"]["OutlineNodeScope"] | components["schemas"]["NovelScope"];
            selectionTarget?: components["schemas"]["SelectionTarget"] | null;
            selectionAttachmentMetadata?: components["schemas"]["SelectionAttachmentMetadata"] | null;
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
            /** Userinstruction */
            userInstruction: string;
        };
        /** ManualVersionRequest */
        ManualVersionRequest: {
            documentType: components["schemas"]["DocumentType"];
            /** Chapterid */
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Baseversionid */
            baseVersionId?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            /** Contenthash */
            contentHash: string;
            /** Confirmationhash */
            confirmationHash: string;
            /** Summary */
            summary?: string | null;
        };
        /** MessageResponse */
        MessageResponse: {
            /** Id */
            id: string;
            /** Sessionid */
            sessionId: string;
            /** Role */
            role: string;
            /** Agentid */
            agentId: string | null;
            /** Content */
            content: string;
            /** Intent */
            intent: string | null;
            metadata: components["schemas"]["JsonValue"] | null;
            /** Parentid */
            parentId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** NovelResponse */
        NovelResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Summary */
            summary: string | null;
            /** Storyprogress */
            storyProgress: string | null;
            /** Appliedstyleid */
            appliedStyleId: string | null;
            storyLengthProfile?: components["schemas"]["StoryLengthProfile"] | null;
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Id */
            id: string;
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** OutlineNodeDto */
        OutlineNodeDto: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Content */
            content: string | null;
            kind: components["schemas"]["OutlineNodeKind"];
            status: components["schemas"]["OutlineNodeStatus"];
            /** Order */
            order: number;
            /** Parentid */
            parentId: string | null;
            /** Linkedchapterid */
            linkedChapterId: string | null;
            /** Estimatedwordcount */
            estimatedWordCount: number | null;
            /** Actualwordcount */
            actualWordCount: number | null;
            /** Chapterstartorder */
            chapterStartOrder: number | null;
            /** Chapterendorder */
            chapterEndOrder: number | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Title */
            title: string;
            /** Content */
            content?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /**
             * Order
             * @default 0
             */
            order: number;
            /** Parentid */
            parentId?: string | null;
            /** Linkedchapterid */
            linkedChapterId?: string | null;
            /** Estimatedwordcount */
            estimatedWordCount?: number | null;
            /** Actualwordcount */
            actualWordCount?: number | null;
            /** Chapterstartorder */
            chapterStartOrder?: number | null;
            /** Chapterendorder */
            chapterEndOrder?: number | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Effective */
            effective: boolean;
        };
        /** OutlineNodeResponse */
        OutlineNodeResponse: {
            /** Title */
            title: string;
            /** Content */
            content?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "stage" | "plot_unit" | "chapter_group";
            /**
             * Status
             * @default planned
             * @enum {string}
             */
            status: "planned" | "in_progress" | "completed" | "skipped";
            /**
             * Order
             * @default 0
             */
            order: number;
            /** Parentid */
            parentId?: string | null;
            /** Linkedchapterid */
            linkedChapterId?: string | null;
            /** Estimatedwordcount */
            estimatedWordCount?: number | null;
            /** Actualwordcount */
            actualWordCount?: number | null;
            /** Chapterstartorder */
            chapterStartOrder?: number | null;
            /** Chapterendorder */
            chapterEndOrder?: number | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
        /** PlotProgressDto */
        PlotProgressDto: {
            /** Id */
            id: string;
            /** Currentstage */
            currentStage: string;
            /** Currentgoal */
            currentGoal: string | null;
            /** Currentconflict */
            currentConflict: string | null;
            /** Nextmilestone */
            nextMilestone: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** PlotProgressRequest */
        PlotProgressRequest: {
            /** Currentstage */
            currentStage: string;
            /** Currentgoal */
            currentGoal?: string | null;
            /** Currentconflict */
            currentConflict?: string | null;
            /** Nextmilestone */
            nextMilestone?: string | null;
            /** Expectedupdatedat */
            expectedUpdatedAt: string | null;
        };
        /** PlotProgressResponse */
        PlotProgressResponse: {
            /** Currentstage */
            currentStage: string;
            /** Currentgoal */
            currentGoal?: string | null;
            /** Currentconflict */
            currentConflict?: string | null;
            /** Nextmilestone */
            nextMilestone?: string | null;
            /** Id */
            id: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** PortraitAcceptedResponse */
        PortraitAcceptedResponse: {
            /** Taskid */
            taskId: string;
            /**
             * Status
             * @constant
             */
            status: "pending";
        };
        /** PortraitTaskResponse */
        PortraitTaskResponse: {
            /** Id */
            id: string;
            /** Styleid */
            styleId: string;
            /** Section */
            section: ("creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits") | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "processing" | "success" | "error";
            /** Errormessage */
            errorMessage: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** QualityCheckDto */
        QualityCheckDto: {
            /** Id */
            id: string;
            /** Chapterid */
            chapterId: string;
            type: components["schemas"]["QualityCheckType"];
            status: components["schemas"]["QualityCheckStatus"];
            /** Title */
            title: string;
            /** Summary */
            summary: string | null;
            /** Result */
            result: string | null;
            /** Scorehook */
            scoreHook: number | null;
            /** Scoretension */
            scoreTension: number | null;
            /** Scorepayoff */
            scorePayoff: number | null;
            /** Scorepacing */
            scorePacing: number | null;
            /** Scoreendinghook */
            scoreEndingHook: number | null;
            /** Scorereaderpromise */
            scoreReaderPromise: number | null;
            /** Scoreoverall */
            scoreOverall: number | null;
            qualityGate: components["schemas"]["QualityGate"] | null;
            /** Rewritebrief */
            rewriteBrief: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Title */
            title: string;
            /** Sourceid */
            sourceId: string;
            /** Chunkindex */
            chunkIndex: number;
            /** Score */
            score: number;
            /** Text */
            text: string;
        };
        /** ReadyHealthResponse */
        ReadyHealthResponse: {
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "not_ready";
            /**
             * Service
             * @constant
             */
            service: "core-api";
            /** Checks */
            checks: {
                [key: string]: "ok" | "failed";
            };
            /** Backgroundtasks */
            backgroundTasks?: {
                [key: string]: string;
            } | null;
        };
        /** ReferenceDto */
        ReferenceDto: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            type: components["schemas"]["ReferenceType"];
            /** Content */
            content: string;
            /** Sourceurl */
            sourceUrl: string | null;
            ragStatus: components["schemas"]["RagDocumentStatus"];
            /** Contenthash */
            contentHash: string;
            /** Errormessage */
            errorMessage: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ReferenceMaterialResponse */
        ReferenceMaterialResponse: {
            /** Title */
            title: string;
            /**
             * Type
             * @enum {string}
             */
            type: "note" | "web" | "book" | "image" | "custom";
            /** Content */
            content: string;
            /** Sourceurl */
            sourceUrl?: string | null;
            /** Id */
            id: string;
            /**
             * Ragstatus
             * @enum {string}
             */
            ragStatus: "disabled" | "ready" | "failed";
            /** Contenthash */
            contentHash: string;
            /** Errormessage */
            errorMessage: string | null;
            /** Createdat */
            createdAt?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** @enum {string} */
        ReferenceType: "note" | "web" | "book" | "image" | "custom";
        /** RegisterRequest */
        RegisterRequest: {
            /** Username */
            username: string;
            /**
             * Password
             * Format: password
             */
            password: string;
            /**
             * Confirmpassword
             * Format: password
             */
            confirmPassword: string;
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
            /** Targetid */
            targetId: string;
            /**
             * Relationtype
             * @enum {string}
             */
            relationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
            /**
             * Intimacy
             * @default 0
             */
            intimacy: number;
            /** Description */
            description?: string | null;
            /** Startdate */
            startDate?: string | null;
            /** Enddate */
            endDate?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** @enum {string} */
        RelationType: "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";
        /** ResumeWritingRunRequest */
        ResumeWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Writingsessionid */
            writingSessionId?: string | null;
            /** Usermessage */
            userMessage?: string | null;
        };
        /** ResumeWritingRunResponse */
        ResumeWritingRunResponse: {
            /**
             * Accepted
             * @constant
             */
            accepted: true;
            /** Taskid */
            taskId: string;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
        };
        /** ReviewArtifactDecisionRequest */
        ReviewArtifactDecisionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "discard" | "revise";
            /** Editedcontent */
            editedContent?: string | null;
            /** Editedreplacement */
            editedReplacement?: string | null;
            /** Selectedupdaterefs */
            selectedUpdateRefs?: components["schemas"]["ArtifactSelectionRef"][] | null;
            /** Usermessage */
            userMessage?: string | null;
        };
        /** ReviewArtifactListResponse */
        ReviewArtifactListResponse: {
            /** Items */
            items: components["schemas"]["ReviewArtifactResponse"][];
            /** Nextcursor */
            nextCursor: string | null;
        };
        /** ReviewArtifactResponse */
        ReviewArtifactResponse: {
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Taskid */
            taskId: string | null;
            /** Workflowrunid */
            workflowRunId: string | null;
            /** Artifactkey */
            artifactKey: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "agent_updates" | "outline_draft" | "chapter_draft" | "lore_draft" | "revision_brief" | "beat_plan_draft" | "chapter_content" | "beat_plan" | "freeform_markdown";
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "under_review" | "awaiting_user" | "applying" | "applied";
            /** Title */
            title: string | null;
            /** Summary */
            summary: string | null;
            /** Payload */
            payload: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            diff: components["schemas"]["JsonValue"] | null;
            /** Createdbyagent */
            createdByAgent: string | null;
            /** Updatedbyagent */
            updatedByAgent: string | null;
            /** Revieweragent */
            reviewerAgent: string | null;
            /** Revision */
            revision: number;
            /** Evaluations */
            evaluations?: components["schemas"]["ArtifactEvaluationResponse"][];
            /** Sourcebindings */
            sourceBindings: components["schemas"]["SourceBinding"][] | null;
            /**
             * Sourcebindingstatus
             * @enum {string}
             */
            sourceBindingStatus: "verified" | "legacy_missing" | "not_yet_supported";
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** RunQualityCheckRequest */
        RunQualityCheckRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Taskid */
            taskId?: string | null;
            /** Message */
            message?: string | null;
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
        /** SaveEpisodePlanRequest */
        SaveEpisodePlanRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedadaptationrevision */
            expectedAdaptationRevision: number;
            /** Shotplanversionid */
            shotPlanVersionId: string;
            /** Breakaftershotids */
            breakAfterShotIds?: string[];
        };
        /** SaveShotPromptRequest */
        SaveShotPromptRequest: {
            /** Expectedpromptrevision */
            expectedPromptRevision: number;
            /** Candidatetaskid */
            candidateTaskId?: string | null;
            /** Currentprompt */
            currentPrompt: string;
        };
        /** SaveShotVisualReferencesRequest */
        SaveShotVisualReferencesRequest: {
            /** Expectedrevision */
            expectedRevision: number;
            /** References */
            references?: components["schemas"]["ShotVisualReferenceSelectionRequest"][];
        };
        /** SceneBeatDto */
        SceneBeatDto: {
            /** Id */
            id: string;
            /** Order */
            order: number;
            /** Goal */
            goal: string;
            /** Conflict */
            conflict: string | null;
            /** Characters */
            characters: string;
            /** Foreshadowingrefs */
            foreshadowingRefs: string | null;
            /** Estimatedwords */
            estimatedWords: number;
            /** Acceptancecriteria */
            acceptanceCriteria: string;
        };
        /**
         * SeedanceShotPromptSpec
         * @description 模型只填结构化内容，最终即梦文本由纯函数按固定顺序编译。
         */
        SeedanceShotPromptSpec: {
            /** Subjectandscene */
            subjectAndScene: string;
            /** Visibleaction */
            visibleAction: string;
            /** Performance */
            performance?: string | null;
            /** Expressionandgaze */
            expressionAndGaze?: string | null;
            /** Camera */
            camera: string;
            /** Audio */
            audio: string;
            /** Continuity */
            continuity?: string | null;
            /** Negativeconstraints */
            negativeConstraints?: string[];
        };
        /**
         * SelectionAttachmentMetadata
         * @description 选区来源快照的 UI 元数据；不包含也不承载权威正文。
         */
        SelectionAttachmentMetadata: {
            /**
             * Resourcetype
             * @enum {string}
             */
            resourceType: "chapter_content" | "outline_content" | "outline_node_content";
            /** Resourceid */
            resourceId: string;
            /** Sourcelabel */
            sourceLabel: string;
            /**
             * Baseupdatedat
             * Format: date-time
             */
            baseUpdatedAt: string;
            /** Basecontenthash */
            baseContentHash: string;
            /** Selectionstart */
            selectionStart: number;
            /** Selectionend */
            selectionEnd: number;
            /** Selectedtexthash */
            selectedTextHash: string;
            /** Selectionpreview */
            selectionPreview: string;
        };
        /**
         * SelectionTarget
         * @description 客户端提交的不可变选区身份；正文由 Core 从权威源派生。
         */
        SelectionTarget: {
            /**
             * Resourcetype
             * @enum {string}
             */
            resourceType: "chapter_content" | "outline_content" | "outline_node_content";
            /** Resourceid */
            resourceId: string;
            /**
             * Baseupdatedat
             * Format: date-time
             */
            baseUpdatedAt: string;
            /** Basecontenthash */
            baseContentHash: string;
            /** Selectionstart */
            selectionStart: number;
            /** Selectionend */
            selectionEnd: number;
            /** Selectedtexthash */
            selectedTextHash: string;
        };
        /** @enum {string} */
        ShortMediumSourceKind: "idea" | "opening" | "ending" | "outline" | "mixed";
        /** ShortMediumStartWritingRunRequest */
        ShortMediumStartWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Workflow
             * @constant
             */
            workflow: "short_medium";
            /** Novelid */
            novelId: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "generate_outline" | "generate_manuscript" | "replace_selection" | "full_check";
            /**
             * Documenttype
             * @enum {string}
             */
            documentType: "outline" | "manuscript";
            /** Chapterid */
            chapterId?: string | null;
            /** Baseversionid */
            baseVersionId?: string | null;
            /** Sourceoutlineversionid */
            sourceOutlineVersionId?: string | null;
            /** Selectionstart */
            selectionStart?: number | null;
            /** Selectionend */
            selectionEnd?: number | null;
            /** Selectedtexthash */
            selectedTextHash?: string | null;
            /** Userinstruction */
            userInstruction?: string | null;
        };
        /** ShotPromptCandidateResponse */
        ShotPromptCandidateResponse: {
            /** Taskid */
            taskId: string;
            /** Shotid */
            shotId: string;
            /** Shotkey */
            shotKey: string;
            spec: components["schemas"]["SeedanceShotPromptSpec"];
            /** Compiledprompt */
            compiledPrompt: string;
            /** Visualreferences */
            visualReferences: components["schemas"]["ShotVisualReferenceSnapshot"][];
            /** Qualitywarnings */
            qualityWarnings?: string[];
        };
        /** ShotPromptVersionResponse */
        ShotPromptVersionResponse: {
            /** Id */
            id: string;
            /** Shotid */
            shotId: string;
            /** Shotkey */
            shotKey: string;
            /** Versionno */
            versionNo: number;
            /** Generatedtext */
            generatedText: string | null;
            /** Currenttext */
            currentText: string;
            /** Promptedited */
            promptEdited: boolean;
            /** Visualreferences */
            visualReferences: components["schemas"]["ShotVisualReferenceSnapshot"][];
            /** Headrevision */
            headRevision: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** ShotVisualReferenceSelectionRequest */
        ShotVisualReferenceSelectionRequest: {
            /** Canonversionid */
            canonVersionId: string;
            /** Strength */
            strength: number;
        };
        /** ShotVisualReferenceSetResponse */
        ShotVisualReferenceSetResponse: {
            /** Shotid */
            shotId: string;
            /** Shotkey */
            shotKey: string;
            /** Revision */
            revision: number;
            /** References */
            references: components["schemas"]["ShotVisualReferenceSnapshot"][];
        };
        /**
         * ShotVisualReferenceSnapshot
         * @description 提示词与后续视频请求共同冻结的一份正式视觉参考。
         */
        ShotVisualReferenceSnapshot: {
            /** Canonversionid */
            canonVersionId: string;
            /** Assetid */
            assetId: string;
            /** Assetsha256 */
            assetSha256: string;
            /**
             * Settingkind
             * @enum {string}
             */
            settingKind: "character" | "location" | "item";
            /** Settingid */
            settingId: string;
            /** Settingname */
            settingName: string;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Variantkey */
            variantKey: string;
            /** Label */
            label: string;
            /** Includefeatures */
            includeFeatures?: string[];
            /** Excludefeatures */
            excludeFeatures?: string[];
            /** Strength */
            strength: number;
        };
        /** SourceBinding */
        SourceBinding: {
            /** Resourcetype */
            resourceType: string;
            /** Resourceid */
            resourceId: string;
            /** Exists */
            exists: boolean;
            /** Updatedat */
            updatedAt: string | null;
            /** Contentsha256 */
            contentSha256: string | null;
            /** Revision */
            revision: number | null;
            absenceSentinel: components["schemas"]["AbsenceSentinel"] | null;
        };
        /** StartPromptRunRequest */
        StartPromptRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedadaptationrevision */
            expectedAdaptationRevision: number;
            /** Shotplanversionid */
            shotPlanVersionId: string;
            /** Shotids */
            shotIds?: string[];
        };
        /** StartShotPlanRunRequest */
        StartShotPlanRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Pacingpreset
             * @default short_drama
             * @enum {string}
             */
            pacingPreset: "short_drama" | "cinematic" | "dialogue_driven";
            /**
             * Targetepisodeseconds
             * @default 90
             * @enum {integer}
             */
            targetEpisodeSeconds: 60 | 90 | 120;
            /** Baseshotplanversionid */
            baseShotPlanVersionId?: string | null;
            /** Revisionbrief */
            revisionBrief?: string | null;
        };
        /** StartWritingRunRequest */
        StartWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId?: string | null;
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
            /** Selectedagents */
            selectedAgents?: ("设定" | "剧情" | "写作" | "校验" | "编辑")[];
            /** Usermessage */
            userMessage: string;
        };
        /** @enum {string} */
        StoryLengthProfile: "short_medium" | "long_serial";
        /** StyleReferenceResponse */
        StyleReferenceResponse: {
            /** Id */
            id: string;
            /** Styleid */
            styleId: string;
            /** Filename */
            filename: string;
            /** Charcount */
            charCount: number;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "error";
            /** Errormessage */
            errorMessage: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** StyleResponse */
        StyleResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Sourcetype
             * @enum {string}
             */
            sourceType: "manual" | "agent";
            /** Creativemethodology */
            creativeMethodology: string | null;
            /** Uniquemarkers */
            uniqueMarkers: string | null;
            /** Generationstyle */
            generationStyle: string | null;
            /** Expressionfeatures */
            expressionFeatures: string | null;
            /** Styletraits */
            styleTraits: string | null;
            /** Portraitmarkdown */
            portraitMarkdown: string | null;
            /** Originalcharcount */
            originalCharCount: number;
            /** Usedcharcount */
            usedCharCount: number;
            /** Truncated */
            truncated: boolean;
            /** Errormessage */
            errorMessage: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** References */
            references: components["schemas"]["StyleReferenceResponse"][];
            /** Tasks */
            tasks: components["schemas"]["PortraitTaskResponse"][];
        };
        /** @enum {string} */
        StyleSourceType: "manual" | "agent";
        /** StyleSummary */
        StyleSummary: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Portraitmarkdown */
            portraitMarkdown?: string | null;
            sourceType: components["schemas"]["StyleSourceType"];
        };
        /** TaskModelUsageCall */
        TaskModelUsageCall: {
            /** Requestid */
            requestId: string;
            /** Runid */
            runId: string;
            /** Agentid */
            agentId: string | null;
            /** Model */
            model: string;
            /** Prompttokens */
            promptTokens: number;
            /** Cachedtokens */
            cachedTokens: number;
            /** Completiontokens */
            completionTokens: number;
            /** Totaltokens */
            totalTokens: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** TaskModelUsageResponse */
        TaskModelUsageResponse: {
            /** Taskid */
            taskId: string;
            /** Requestcount */
            requestCount: number;
            /** Prompttokens */
            promptTokens: number;
            /** Cachedtokens */
            cachedTokens: number;
            /** Completiontokens */
            completionTokens: number;
            /** Totaltokens */
            totalTokens: number;
            /** Calls */
            calls: components["schemas"]["TaskModelUsageCall"][];
        };
        /** TokenUsageBreakdown */
        TokenUsageBreakdown: {
            /** Prompttokens */
            promptTokens: number;
            /** Cachedtokens */
            cachedTokens: number;
            /** Completiontokens */
            completionTokens: number;
            /** Totaltokens */
            totalTokens: number;
        };
        /** UpdateChapterRequest */
        UpdateChapterRequest: {
            /** Title */
            title: string;
            /** Content */
            content: string;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateCharacterRequest */
        UpdateCharacterRequest: {
            /** Name */
            name?: string | null;
            /** Aliases */
            aliases?: string | null;
            /** Gender */
            gender?: string | null;
            /** Age */
            age?: string | null;
            /** Appearance */
            appearance?: string | null;
            /** Personality */
            personality?: string | null;
            /** Identity */
            identity?: string | null;
            /** Background */
            background?: string | null;
            /** Coredesire */
            coreDesire?: string | null;
            /** Behaviorboundaries */
            behaviorBoundaries?: string | null;
            /** Speechstyle */
            speechStyle?: string | null;
            /** Relationshipprinciples */
            relationshipPrinciples?: string | null;
            /** Shorttermgoal */
            shortTermGoal?: string | null;
            /** Factionid */
            factionId?: string | null;
            /** Powerlevel */
            powerLevel?: string | null;
            /** Combatability */
            combatAbility?: string | null;
            /** Specialskills */
            specialSkills?: string | null;
            /** Currentstatus */
            currentStatus?: ("active" | "missing" | "dead" | "imprisoned" | "unknown") | null;
            /** Statusnote */
            statusNote?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateExperienceRequest */
        UpdateExperienceRequest: {
            /** Chapterid */
            chapterId?: string | null;
            /** Content */
            content?: string | null;
            /** Order */
            order?: number | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateFactionRequest */
        UpdateFactionRequest: {
            /** Name */
            name?: string | null;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Baseid */
            baseId?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateForeshadowingRequest */
        UpdateForeshadowingRequest: {
            /** Name */
            name?: string | null;
            /** Plantedat */
            plantedAt?: string | null;
            /** Plantedcontent */
            plantedContent?: string | null;
            /** Expectedpayoff */
            expectedPayoff?: string | null;
            /** Payoffat */
            payoffAt?: string | null;
            /** Status */
            status?: ("active" | "paid_off" | "abandoned") | null;
        };
        /** UpdateGlossaryRequest */
        UpdateGlossaryRequest: {
            /** Term */
            term?: string | null;
            /** Definition */
            definition?: string | null;
            /** Category */
            category?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateItemRequest */
        UpdateItemRequest: {
            /** Name */
            name?: string | null;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Rarity */
            rarity?: string | null;
            /** Effect */
            effect?: string | null;
            /** Origin */
            origin?: string | null;
            /** Description */
            description?: string | null;
            /** Ownerid */
            ownerId?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateLocationRequest */
        UpdateLocationRequest: {
            /** Name */
            name?: string | null;
            /** Aliases */
            aliases?: string | null;
            /** Type */
            type?: string | null;
            /** Parentid */
            parentId?: string | null;
            /** Climate */
            climate?: string | null;
            /** Culture */
            culture?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateNovelSummaryRequest */
        UpdateNovelSummaryRequest: {
            /** Summary */
            summary: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateOutlineNodeRequest */
        UpdateOutlineNodeRequest: {
            /** Title */
            title?: string | null;
            /** Content */
            content?: string | null;
            /** Kind */
            kind?: ("stage" | "plot_unit" | "chapter_group") | null;
            /** Status */
            status?: ("planned" | "in_progress" | "completed" | "skipped") | null;
            /** Order */
            order?: number | null;
            /** Parentid */
            parentId?: string | null;
            /** Linkedchapterid */
            linkedChapterId?: string | null;
            /** Estimatedwordcount */
            estimatedWordCount?: number | null;
            /** Actualwordcount */
            actualWordCount?: number | null;
            /** Chapterstartorder */
            chapterStartOrder?: number | null;
            /** Chapterendorder */
            chapterEndOrder?: number | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdatePortraitSectionRequest */
        UpdatePortraitSectionRequest: {
            /** Content */
            content: string;
        };
        /** UpdateQualityCheckRequest */
        UpdateQualityCheckRequest: {
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "skipped";
            /**
             * Resetresult
             * @default false
             */
            resetResult: boolean;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateReferenceRequest */
        UpdateReferenceRequest: {
            /** Title */
            title?: string | null;
            /** Type */
            type?: ("note" | "web" | "book" | "image" | "custom") | null;
            /** Content */
            content?: string | null;
            /** Sourceurl */
            sourceUrl?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateRelationRequest */
        UpdateRelationRequest: {
            /** Relationtype */
            relationType?: ("family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other") | null;
            /** Intimacy */
            intimacy?: number | null;
            /** Description */
            description?: string | null;
            /** Startdate */
            startDate?: string | null;
            /** Enddate */
            endDate?: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateWritingSessionRequest */
        UpdateWritingSessionRequest: {
            /** Title */
            title?: string | null;
            /** Phase */
            phase?: ("idle" | "discussing" | "generating" | "recording" | "completed") | null;
        };
        /** UserResponse */
        UserResponse: {
            /** Id */
            id: string;
            /** Username */
            username: string;
            /** Creditbalancemicros */
            creditBalanceMicros: string;
        };
        /** VersionActionRequest */
        VersionActionRequest: {
            documentType: components["schemas"]["DocumentType"];
            /** Chapterid */
            chapterId?: string | null;
            /** Clientrequestid */
            clientRequestId: string;
            /** Baseversionid */
            baseVersionId?: string | null;
            /** Confirmationhash */
            confirmationHash: string;
        };
        /** VersionDetailResponse */
        VersionDetailResponse: {
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Artifactkey */
            artifactKey: string;
            status: components["schemas"]["VersionStatus"];
            /** Summary */
            summary: string | null;
            payload: components["schemas"]["DocumentVersionPayload"];
            documentType: components["schemas"]["DocumentType"];
            /** Versionnumber */
            versionNumber: number;
            source: components["schemas"]["VersionSource"];
            /** Content */
            content: string;
            /** Contenthash */
            contentHash: string;
            /** Baseversionid */
            baseVersionId: string | null;
            /** Sourceoutlineversionid */
            sourceOutlineVersionId: string | null;
            /** Restoredfromversionid */
            restoredFromVersionId: string | null;
            diff: components["schemas"]["VersionDiffResponse"] | null;
            /** Createdbyagent */
            createdByAgent: string | null;
            /** Taskid */
            taskId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Appliedat */
            appliedAt: string | null;
        };
        /** VersionDiffResponse */
        VersionDiffResponse: {
            /** Fromversionid */
            fromVersionId: string | null;
            /** Toversionid */
            toVersionId: string | null;
            /** Fromwordcount */
            fromWordCount: number;
            /** Towordcount */
            toWordCount: number;
            /** Wordcountdelta */
            wordCountDelta: number;
            /** Blocks */
            blocks: components["schemas"]["DiffBlock"][];
            /** Confirmationhash */
            confirmationHash: string;
        };
        /** VersionListItem */
        VersionListItem: {
            /** Id */
            id: string;
            documentType: components["schemas"]["DocumentType"];
            /** Versionnumber */
            versionNumber: number;
            status: components["schemas"]["VersionStatus"];
            source: components["schemas"]["VersionSource"];
            /** Wordcount */
            wordCount: number;
            /** Baseversionid */
            baseVersionId: string | null;
            /** Sourceoutlineversionid */
            sourceOutlineVersionId: string | null;
            /** Restoredfromversionid */
            restoredFromVersionId: string | null;
            /** Summary */
            summary: string | null;
            /** Createdbyagent */
            createdByAgent: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Appliedat */
            appliedAt: string | null;
        };
        /** VersionPreviewRequest */
        VersionPreviewRequest: {
            documentType: components["schemas"]["DocumentType"];
            /** Chapterid */
            chapterId?: string | null;
            /** Baseversionid */
            baseVersionId?: string | null;
        };
        /** VersionPreviewResponse */
        VersionPreviewResponse: {
            documentType: components["schemas"]["DocumentType"];
            /** Chapterid */
            chapterId: string | null;
            /** Baseversionid */
            baseVersionId: string | null;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
            /** Contenthash */
            contentHash: string;
            /** Dirty */
            dirty: boolean;
            /** Confirmationsummary */
            confirmationSummary: string;
            /** Confirmationhash */
            confirmationHash: string;
            diff: components["schemas"]["VersionDiffResponse"];
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
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Name */
            name: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "image" | "video" | "audio";
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "music";
            /** Mimetype */
            mimeType: string;
            /** Bytesize */
            byteSize: number;
            /** Durationms */
            durationMs: number | null;
            /** Sha256 */
            sha256: string;
            /** Sourcekind */
            sourceKind: string;
            /** Rightsstatus */
            rightsStatus: string;
            /** Lockedat */
            lockedAt: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /**
         * VideoProjectDetailResponse
         * @description 章节影视化工作台加载项目素材所需的公共信息。
         */
        VideoProjectDetailResponse: {
            project: components["schemas"]["VideoProjectResponse"];
            /** Assets */
            assets: components["schemas"]["VideoAssetResponse"][];
            /** Previewenabled */
            previewEnabled: boolean;
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
            /** Projects */
            projects: components["schemas"]["VideoProjectResponse"][];
            /** Previewenabled */
            previewEnabled: boolean;
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
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Title */
            title: string;
            /** Mode */
            mode: string;
            /** Status */
            status: string;
            /** Targetaspectratio */
            targetAspectRatio: string;
            /** Targetlanguage */
            targetLanguage: string;
            /** Provider */
            provider: string;
            /** Revision */
            revision: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VisualCanonLibraryResponse */
        VisualCanonLibraryResponse: {
            /** Canons */
            canons: components["schemas"]["VisualCanonResponse"][];
        };
        /** VisualCanonResponse */
        VisualCanonResponse: {
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Novelid */
            novelId: string;
            /**
             * Settingkind
             * @enum {string}
             */
            settingKind: "character" | "location" | "item";
            /** Settingid */
            settingId: string;
            /** Settingname */
            settingName: string;
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Variantkey */
            variantKey: string;
            /** Label */
            label: string;
            candidateAsset: components["schemas"]["VideoAssetResponse"] | null;
            /** Candidateincludefeatures */
            candidateIncludeFeatures: string[];
            /** Candidateexcludefeatures */
            candidateExcludeFeatures: string[];
            /** Candidatedefaultstrength */
            candidateDefaultStrength: number | null;
            /** Currentversionid */
            currentVersionId: string | null;
            /** Versions */
            versions: components["schemas"]["VisualCanonVersionResponse"][];
            /** Revision */
            revision: number;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VisualCanonVersionResponse */
        VisualCanonVersionResponse: {
            /** Id */
            id: string;
            /** Canonid */
            canonId: string;
            /** Versionno */
            versionNo: number;
            asset: components["schemas"]["VideoAssetResponse"];
            /** Settingname */
            settingName: string;
            /** Label */
            label: string;
            /** Includefeatures */
            includeFeatures: string[];
            /** Excludefeatures */
            excludeFeatures: string[];
            /** Defaultstrength */
            defaultStrength: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** WorkflowRunDetailResponse */
        WorkflowRunDetailResponse: {
            summary: components["schemas"]["WorkflowRunSummary"];
            /** Content */
            content: string;
        };
        /** WorkflowRunListResponse */
        WorkflowRunListResponse: {
            /** Runs */
            runs: components["schemas"]["WorkflowRunSummary"][];
        };
        /** WorkflowRunSummary */
        WorkflowRunSummary: {
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string;
            /** Runkind */
            runKind: string;
            /** Userid */
            userId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string | null;
            /** Startedat */
            startedAt: string;
            /** Endedat */
            endedAt: string;
            /** Status */
            status: string;
        };
        /** WorkspaceBootstrapResponse */
        WorkspaceBootstrapResponse: {
            novel: components["schemas"]["WorkspaceNovel"];
            /** Chapters */
            chapters: components["schemas"]["WorkspaceChapterSummary"][];
            currentChapter: components["schemas"]["WorkspaceChapter"] | null;
            /** Currentchapterid */
            currentChapterId: string | null;
        };
        /** WorkspaceChapter */
        WorkspaceChapter: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Content */
            content: string;
            /** Order */
            order: number;
            status: components["schemas"]["ChapterStatus"];
            /** Completedat */
            completedAt: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Wordcount */
            wordCount: number;
            progress: components["schemas"]["ChapterProgressDto"] | null;
            /** Qualitychecks */
            qualityChecks: components["schemas"]["QualityCheckDto"][];
            approvedBeatPlan: components["schemas"]["BeatPlanDto"] | null;
        };
        /** WorkspaceChapterSummary */
        WorkspaceChapterSummary: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Order */
            order: number;
            status: components["schemas"]["ChapterStatus"];
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Wordcount */
            wordCount: number;
            approvedBeatPlan: components["schemas"]["ApprovedBeatPlanSummary"] | null;
        };
        /** WorkspaceLoreResponse */
        WorkspaceLoreResponse: {
            /** Characters */
            characters: components["schemas"]["CharacterDto"][];
            /** Items */
            items: components["schemas"]["ItemDto"][];
            /** Locations */
            locations: components["schemas"]["LocationDto"][];
            /** Factions */
            factions: components["schemas"]["FactionDto"][];
            /** Glossaries */
            glossaries: components["schemas"]["GlossaryDto"][];
        };
        /** WorkspaceNovel */
        WorkspaceNovel: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Summary */
            summary: string | null;
            /** Storyprogress */
            storyProgress: string | null;
            /** Appliedstyleid */
            appliedStyleId: string | null;
            storyLengthProfile?: components["schemas"]["StoryLengthProfile"] | null;
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
        };
        /** WorkspacePlanningResponse */
        WorkspacePlanningResponse: {
            /** Storyprogress */
            storyProgress: string | null;
            /**
             * Storyprogressupdatedat
             * Format: date-time
             */
            storyProgressUpdatedAt: string;
            storyBackground: components["schemas"]["ContentDto"] | null;
            worldSetting: components["schemas"]["ContentDto"] | null;
            writingBible: components["schemas"]["WritingBibleDto"] | null;
            outline: components["schemas"]["ContentDto"] | null;
            /** Outlinenodes */
            outlineNodes: components["schemas"]["OutlineNodeDto"][];
            plotProgress: components["schemas"]["PlotProgressDto"] | null;
        };
        /** WorkspaceResourcesResponse */
        WorkspaceResourcesResponse: {
            /** References */
            references: components["schemas"]["ReferenceDto"][];
            /** Styles */
            styles: components["schemas"]["StyleSummary"][];
            appliedStyle: components["schemas"]["AppliedStyleSummary"] | null;
        };
        /** WorkspaceResponse */
        WorkspaceResponse: {
            novel: components["schemas"]["WorkspaceNovel"];
            /** Chapters */
            chapters: components["schemas"]["WorkspaceChapter"][];
            /** Currentchapterid */
            currentChapterId: string | null;
            /** Characters */
            characters: components["schemas"]["CharacterDto"][];
            /** Items */
            items: components["schemas"]["ItemDto"][];
            /** Locations */
            locations: components["schemas"]["LocationDto"][];
            /** Factions */
            factions: components["schemas"]["FactionDto"][];
            /** Glossaries */
            glossaries: components["schemas"]["GlossaryDto"][];
            storyBackground: components["schemas"]["ContentDto"] | null;
            worldSetting: components["schemas"]["ContentDto"] | null;
            writingBible: components["schemas"]["WritingBibleDto"] | null;
            outline: components["schemas"]["ContentDto"] | null;
            /** Outlinenodes */
            outlineNodes: components["schemas"]["OutlineNodeDto"][];
            plotProgress: components["schemas"]["PlotProgressDto"] | null;
            /** References */
            references: components["schemas"]["ReferenceDto"][];
            /** Styles */
            styles: components["schemas"]["StyleSummary"][];
        };
        /** WritingBibleDto */
        WritingBibleDto: {
            /** Id */
            id: string;
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount: number | null;
            /** Genre */
            genre: string | null;
            /** Targetreaders */
            targetReaders: string | null;
            /** Coresellingpoint */
            coreSellingPoint: string | null;
            /** Readerpromise */
            readerPromise: string | null;
            /** Appealmodel */
            appealModel: string | null;
            /** Taboo */
            taboo: string | null;
            /** Comparabletitles */
            comparableTitles: string | null;
            /** Notes */
            notes: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingBibleRequest */
        WritingBibleRequest: {
            /** Storylengthprofile */
            storyLengthProfile?: ("short_medium" | "long_serial") | null;
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
            /** Genre */
            genre?: string | null;
            /** Targetreaders */
            targetReaders?: string | null;
            /** Coresellingpoint */
            coreSellingPoint?: string | null;
            /** Readerpromise */
            readerPromise?: string | null;
            /** Appealmodel */
            appealModel?: string | null;
            /** Taboo */
            taboo?: string | null;
            /** Comparabletitles */
            comparableTitles?: string | null;
            /** Notes */
            notes?: string | null;
            /** Expectedupdatedat */
            expectedUpdatedAt: string | null;
        };
        /** WritingBibleResponse */
        WritingBibleResponse: {
            /**
             * Storylengthprofile
             * @enum {string}
             */
            storyLengthProfile: "short_medium" | "long_serial";
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
            /** Genre */
            genre?: string | null;
            /** Targetreaders */
            targetReaders?: string | null;
            /** Coresellingpoint */
            coreSellingPoint?: string | null;
            /** Readerpromise */
            readerPromise?: string | null;
            /** Appealmodel */
            appealModel?: string | null;
            /** Taboo */
            taboo?: string | null;
            /** Comparabletitles */
            comparableTitles?: string | null;
            /** Notes */
            notes?: string | null;
            /** Id */
            id: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingRunCheckpointResponse */
        WritingRunCheckpointResponse: {
            /** Eventsequence */
            eventSequence: number;
            /** Phase */
            phase: string;
            /** Operationstage */
            operationStage: string | null;
            /** Operationstep */
            operationStep: string | null;
        };
        /** WritingRunListItem */
        WritingRunListItem: {
            /** Taskid */
            taskId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId: string | null;
            /**
             * Workflow
             * @enum {string}
             */
            workflow: "long_serial" | "short_medium";
            /** Operation */
            operation: string | null;
            /** Target */
            target: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Scope */
            scope: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Phase */
            phase: string;
            outcome: components["schemas"]["WritingRunOutcome"];
            /** Activeartifactid */
            activeArtifactId: string | null;
            /** Recoverable */
            recoverable: boolean;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingRunListResponse */
        WritingRunListResponse: {
            /** Items */
            items: components["schemas"]["WritingRunListItem"][];
            /** Nextcursor */
            nextCursor: string | null;
        };
        /** WritingRunOutcome */
        WritingRunOutcome: {
            /**
             * State
             * @enum {string}
             */
            state: "queued" | "running" | "waiting_user" | "succeeded" | "failed" | "cancelled" | "inconsistent";
            /** Code */
            code: string;
            /** Taskterminal */
            taskTerminal: boolean;
            /** Streamshouldclose */
            streamShouldClose: boolean;
            /** Reconciliationrequired */
            reconciliationRequired: boolean;
            currentCommand: components["schemas"]["WritingRunOutcomeCommand"] | null;
            result: components["schemas"]["WritingRunOutcomeResult"];
            /**
             * Observedat
             * Format: date-time
             */
            observedAt: string;
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
            /**
             * Kind
             * @enum {string}
             */
            kind: "none" | "review_artifact" | "short_candidate" | "check_report" | "final_message";
            /** Ready */
            ready: boolean;
            /** Id */
            id?: string | null;
        };
        /** WritingRunResponse */
        WritingRunResponse: {
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId: string | null;
            /** Phase */
            phase: string;
            /** Targetwordcount */
            targetWordCount: number;
            /** Selectedagents */
            selectedAgents: string[];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Commandid */
            commandId: string;
            /**
             * Commandstatus
             * @enum {string}
             */
            commandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
        };
        /** WritingRunStatusResponse */
        WritingRunStatusResponse: {
            /** Taskid */
            taskId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId?: string | null;
            /**
             * Workflow
             * @default long_serial
             * @enum {string}
             */
            workflow: "long_serial" | "short_medium";
            /** Target */
            target?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Scope */
            scope?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Phase */
            phase: string;
            checkpoint?: components["schemas"]["WritingRunCheckpointResponse"] | null;
            /** Activeartifactid */
            activeArtifactId?: string | null;
            /**
             * Recoverable
             * @default false
             */
            recoverable: boolean;
            /** Reviewreport */
            reviewReport?: string | null;
            /** Createdat */
            createdAt?: string | null;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Commandid */
            commandId: string | null;
            /** Commandstatus */
            commandStatus: ("pending" | "submitted" | "processing" | "succeeded" | "failed") | null;
            /** Operation */
            operation: ("generate_outline" | "generate_manuscript" | "replace_selection" | "full_check" | "plan_chapter" | "rewrite_scene" | "rewrite_chapter_selection" | "rewrite_outline_selection" | "write_chapter" | "review_chapter") | null;
            /** Candidateversionid */
            candidateVersionId: string | null;
            /** Checkreport */
            checkReport: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Error */
            error: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            outcome: components["schemas"]["WritingRunOutcome"];
        };
        /** WritingSessionDetail */
        WritingSessionDetail: {
            currentTask: components["schemas"]["WritingTaskSummary"] | null;
            lastTask: components["schemas"]["WritingTaskSummary"] | null;
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Title */
            title: string | null;
            /** Phase */
            phase: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Messages */
            messages: components["schemas"]["MessageResponse"][];
        };
        /** WritingSessionListItem */
        WritingSessionListItem: {
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Title */
            title: string | null;
            /** Phase */
            phase: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Messagecount */
            messageCount: number;
            lastMessage: components["schemas"]["LastMessageResponse"] | null;
        };
        /** WritingSessionResponse */
        WritingSessionResponse: {
            /** Id */
            id: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Title */
            title: string | null;
            /** Phase */
            phase: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** WritingTaskSummary */
        WritingTaskSummary: {
            /** Id */
            id: string;
            /** Phase */
            phase: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Hasawaitingreviewartifact */
            hasAwaitingReviewArtifact: boolean;
            /** Currentoperation */
            currentOperation: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
            /** Operationstage */
            operationStage: string | null;
            /** Activeartifactid */
            activeArtifactId: string | null;
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
                "application/json": components["schemas"]["StartWritingRunRequest"] | components["schemas"]["ShortMediumStartWritingRunRequest"] | components["schemas"]["LongSerialStartWritingRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WritingRunResponse"];
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
                    "application/json": components["schemas"]["WritingRunStatusResponse"];
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
                    "application/json": components["schemas"]["CancelWritingRunResponse"];
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
            /** @description Successful Response */
            200: {
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
            query?: never;
            header?: never;
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
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewArtifactResponse"];
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
                    "application/json": components["schemas"]["ArtifactDecisionAcceptedResponse"];
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
    list_adaptations_api_v1_video_projects__project_id__chapter_adaptations_get: {
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
                    "application/json": components["schemas"]["ChapterAdaptationListResponse"];
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
    create_adaptation_api_v1_video_projects__project_id__chapter_adaptations_post: {
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
                "application/json": components["schemas"]["CreateChapterAdaptationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    get_adaptation_api_v1_video_chapter_adaptations__adaptation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
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
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    start_shot_plan_api_v1_video_chapter_adaptations__adaptation_id__shot_plan_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartShotPlanRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationTaskAcceptedResponse"];
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
    confirm_shot_plan_api_v1_video_chapter_adaptations__adaptation_id__shot_plan_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfirmAdaptationPlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    discard_candidate_api_v1_video_chapter_adaptations__adaptation_id__candidate_discard_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DiscardAdaptationCandidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    save_episode_plan_api_v1_video_chapter_adaptations__adaptation_id__episode_plan_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveEpisodePlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    start_prompt_run_api_v1_video_chapter_adaptations__adaptation_id__prompt_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartPromptRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationTaskAcceptedResponse"];
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
    save_shot_prompt_api_v1_video_chapter_adaptations__adaptation_id__shots__shot_id__prompt_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
                shot_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveShotPromptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChapterAdaptationResponse"];
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
    save_shot_visual_references_api_v1_video_chapter_adaptations__adaptation_id__shots__shot_id__visual_references_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                adaptation_id: string;
                shot_id: string;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveShotVisualReferencesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShotVisualReferenceSetResponse"];
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
}
