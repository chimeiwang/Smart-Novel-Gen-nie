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
    "/api/v1/novels/{novel_id}/title": {
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
        /** Update Novel Title */
        patch: operations["update_novel_title_api_v1_novels__novel_id__title_patch"];
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
        get?: never;
        put?: never;
        /** Start Writing Run */
        post: operations["start_writing_run_api_v1_writing_runs_post"];
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
    "/api/v1/novels/{novel_id}/short-story/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Short Story Artifacts */
        get: operations["get_short_story_artifacts_api_v1_novels__novel_id__short_story_artifacts_get"];
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
    "/api/v1/review-artifacts/{artifact_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Review Artifact Revisions */
        get: operations["list_review_artifact_revisions_api_v1_review_artifacts__artifact_id__revisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts/{artifact_id}/revisions/{revision}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Review Artifact Revision */
        get: operations["get_review_artifact_revision_api_v1_review_artifacts__artifact_id__revisions__revision__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts/{artifact_id}/revisions/{revision}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Review Artifact Revision */
        post: operations["restore_review_artifact_revision_api_v1_review_artifacts__artifact_id__revisions__revision__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/review-artifacts/{artifact_id}/outline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Short Story Outline */
        put: operations["save_short_story_outline_api_v1_review_artifacts__artifact_id__outline_put"];
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
        /** Body_upload_reference_api_v1_styles__style_id__references_post */
        Body_upload_reference_api_v1_styles__style_id__references_post: {
            /** File */
            file: string;
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
        };
        /** CreateStyleRequest */
        CreateStyleRequest: {
            /** Name */
            name: string;
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
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount: number | null;
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
        /** ExperienceRequest */
        ExperienceRequest: {
            /** Chapterid */
            chapterId?: string | null;
            /** Content */
            content: string;
            /** Order */
            order?: number | null;
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
        /** LongSerialCreateNovelRequest */
        LongSerialCreateNovelRequest: {
            /** Name */
            name: string;
            /** Summary */
            summary?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            storyLengthProfile: "long_serial";
            /** Targettotalwordcount */
            targetTotalWordCount?: number | null;
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
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount: number | null;
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
        /** OutlineContentRequest */
        OutlineContentRequest: {
            /** Content */
            content: string;
        };
        /** OutlineContentResponse */
        OutlineContentResponse: {
            /** Content */
            content: string;
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
            /** Id */
            id: string;
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
            sourceUrl: string | null;
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
        /** RelationPeer */
        RelationPeer: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** RelationRequest */
        RelationRequest: {
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
        /** RestoreArtifactRevisionRequest */
        RestoreArtifactRevisionRequest: {
            /** Expectedrevision */
            expectedRevision: number;
        };
        /** ResumeWritingRunRequest */
        ResumeWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Writingsessionid */
            writingSessionId?: string | null;
            /** Usermessage */
            userMessage?: string | null;
            /** Artifactid */
            artifactId?: string | null;
            /** Decision */
            decision?: ("approve" | "discard" | "revise") | null;
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
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "discard" | "revise";
            /** Expectedrevision */
            expectedRevision: number;
            /** Editedcontent */
            editedContent?: string | null;
            /** Selectedupdaterefs */
            selectedUpdateRefs?: components["schemas"]["ArtifactSelectionRef"][] | null;
            /** Usermessage */
            userMessage?: string | null;
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
            payload: components["schemas"]["ShortStoryOutlineDraft"] | components["schemas"]["ShortStoryChapterDraft"] | {
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
        /** ReviewArtifactRevisionDetail */
        ReviewArtifactRevisionDetail: {
            /** Artifactid */
            artifactId: string;
            /** Revision */
            revision: number;
            /** Summary */
            summary: string | null;
            /** Createdbyagent */
            createdByAgent: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Payload */
            payload: components["schemas"]["ShortStoryOutlineDraft"] | components["schemas"]["ShortStoryChapterDraft"] | {
                [key: string]: components["schemas"]["JsonValue"];
            };
            diff: components["schemas"]["JsonValue"] | null;
        };
        /** ReviewArtifactRevisionSummary */
        ReviewArtifactRevisionSummary: {
            /** Artifactid */
            artifactId: string;
            /** Revision */
            revision: number;
            /** Summary */
            summary: string | null;
            /** Createdbyagent */
            createdByAgent: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** RunQualityCheckRequest */
        RunQualityCheckRequest: {
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
        /** SaveShortStoryOutlineRequest */
        SaveShortStoryOutlineRequest: {
            /** Expectedrevision */
            expectedRevision: number;
            /** Corepremise */
            corePremise: string;
            anchors: components["schemas"]["ShortStoryAnchors"];
            /** Sections */
            sections: components["schemas"]["ShortStoryOutlineSectionEdit"][];
            /**
             * Changesummary
             * @default 用户直接编辑
             */
            changeSummary: string;
            /** Anchorchanges */
            anchorChanges?: string[];
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
        /** ShortMediumCreateNovelRequest */
        ShortMediumCreateNovelRequest: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            storyLengthProfile: "short_medium";
            /** Inspiration */
            inspiration: string;
            /** Targettotalwordcount */
            targetTotalWordCount: number;
            /** Name */
            name?: string | null;
        };
        /** ShortStoryAnchors */
        ShortStoryAnchors: {
            /** Mustkeep */
            mustKeep?: string[];
            /** Confirmed */
            confirmed?: string[];
            /** Avoid */
            avoid?: string[];
        };
        /** ShortStoryArtifactResponse */
        ShortStoryArtifactResponse: {
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
            kind: "outline_draft" | "chapter_draft";
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
            payload: components["schemas"]["ShortStoryOutlineDraft"] | components["schemas"]["ShortStoryChapterDraft"];
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
        /** ShortStoryArtifactsResponse */
        ShortStoryArtifactsResponse: {
            outline: components["schemas"]["ShortStoryArtifactResponse"] | null;
            chapterDraft: components["schemas"]["ShortStoryArtifactResponse"] | null;
            latestTask: components["schemas"]["ShortStoryTaskStatus"] | null;
            workflowSession: components["schemas"]["ShortStoryWorkflowSession"] | null;
        };
        /** ShortStoryChapterDraft */
        ShortStoryChapterDraft: {
            /**
             * Kind
             * @default chapter_draft
             * @constant
             */
            kind: "chapter_draft";
            /**
             * Storylengthprofile
             * @default short_medium
             * @constant
             */
            storyLengthProfile: "short_medium";
            /** Content */
            content: string;
            metadata: components["schemas"]["ShortStoryDraftMetadata"];
        };
        /** ShortStoryDraftMetadata */
        ShortStoryDraftMetadata: {
            /** Sourceoutlineartifactid */
            sourceOutlineArtifactId: string;
            /** Sourceoutlinerevision */
            sourceOutlineRevision: number;
            /** Sourceoutlinehash */
            sourceOutlineHash: string;
            /** Targetwordcount */
            targetWordCount: number;
            /** Actualwordcount */
            actualWordCount: number;
            /** Targetchapterid */
            targetChapterId: string;
            /** Basechapterhash */
            baseChapterHash: string;
            /** Generationcommandid */
            generationCommandId: string;
            /** Automaticrewritecount */
            automaticRewriteCount: number;
            /**
             * Generationreason
             * @enum {string}
             */
            generationReason: "user_request" | "automatic_rewrite";
        };
        /** ShortStoryOutlineDraft */
        ShortStoryOutlineDraft: {
            /**
             * Kind
             * @default outline_draft
             * @constant
             */
            kind: "outline_draft";
            /**
             * Storylengthprofile
             * @default short_medium
             * @constant
             */
            storyLengthProfile: "short_medium";
            /** Originalinspiration */
            originalInspiration: string;
            /** Corepremise */
            corePremise: string;
            anchors: components["schemas"]["ShortStoryAnchors"];
            /** Sections */
            sections: components["schemas"]["ShortStoryOutlineSection"][];
            /**
             * Content
             * @default
             */
            content: string;
            /**
             * Changesummary
             * @default
             */
            changeSummary: string;
            /** Anchorchanges */
            anchorChanges?: string[];
        };
        /** ShortStoryOutlineSection */
        ShortStoryOutlineSection: {
            /** Id */
            id: string;
            /** Title */
            title: string;
            /** Events */
            events: string;
        };
        /** ShortStoryOutlineSectionEdit */
        ShortStoryOutlineSectionEdit: {
            /** Id */
            id?: string | null;
            /** Title */
            title: string;
            /** Events */
            events: string;
        };
        /** ShortStoryTaskStatus */
        ShortStoryTaskStatus: {
            /** Id */
            id: string;
            /** Phase */
            phase: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "develop_short_outline" | "write_short_story";
            /** Activeartifactid */
            activeArtifactId: string | null;
            /** Latestcommandid */
            latestCommandId: string;
            /**
             * Latestcommandstatus
             * @enum {string}
             */
            latestCommandStatus: "pending" | "submitted" | "processing" | "succeeded" | "failed";
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** ShortStoryWorkflowSession */
        ShortStoryWorkflowSession: {
            /** Id */
            id: string;
            /** Phase */
            phase: string;
            currentTask: components["schemas"]["ShortStoryTaskStatus"] | null;
            lastTask: components["schemas"]["ShortStoryTaskStatus"] | null;
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
             * Workflowkind
             * @enum {string}
             */
            workflowKind: "long_serial" | "short_medium";
            /** Operation */
            operation: ("answer_question" | "create_lore" | "revise_lore" | "create_outline" | "revise_outline" | "plan_chapter" | "write_chapter" | "rewrite_scene" | "review_chapter" | "sync_lore" | "manage_foreshadowing" | "develop_short_outline" | "write_short_story") | null;
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
        };
        /** UpdateNovelTitleRequest */
        UpdateNovelTitleRequest: {
            /** Name */
            name: string;
            /**
             * Expectedupdatedat
             * Format: date-time
             */
            expectedUpdatedAt: string;
        };
        /** UpdateNovelTitleResponse */
        UpdateNovelTitleResponse: {
            /** Name */
            name: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
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
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount: number | null;
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
            storyLengthProfile: components["schemas"]["StoryLengthProfile"];
            /** Targettotalwordcount */
            targetTotalWordCount: number | null;
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
        };
        /** WritingBibleResponse */
        WritingBibleResponse: {
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
             * Storylengthprofile
             * @enum {string}
             */
            storyLengthProfile: "short_medium" | "long_serial";
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
                "application/json": components["schemas"]["ShortMediumCreateNovelRequest"] | components["schemas"]["LongSerialCreateNovelRequest"];
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
    update_novel_title_api_v1_novels__novel_id__title_patch: {
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
                "application/json": components["schemas"]["UpdateNovelTitleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UpdateNovelTitleResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
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
                "application/json": components["schemas"]["ExperienceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
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
                "application/json": components["schemas"]["ExperienceRequest"];
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
                "application/json": components["schemas"]["RelationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
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
                    "application/json": components["schemas"]["OutlineNodeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
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
                    "application/json": components["schemas"]["OutlineNodeResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
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
        requestBody?: never;
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
                "application/json": components["schemas"]["StartWritingRunRequest"];
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
    get_short_story_artifacts_api_v1_novels__novel_id__short_story_artifacts_get: {
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
                    "application/json": components["schemas"]["ShortStoryArtifactsResponse"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
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
    list_review_artifact_revisions_api_v1_review_artifacts__artifact_id__revisions_get: {
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
                    "application/json": components["schemas"]["ReviewArtifactRevisionSummary"][];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_review_artifact_revision_api_v1_review_artifacts__artifact_id__revisions__revision__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
                revision: number;
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
                    "application/json": components["schemas"]["ReviewArtifactRevisionDetail"];
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    restore_review_artifact_revision_api_v1_review_artifacts__artifact_id__revisions__revision__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
                revision: number;
            };
            cookie?: {
                "inkforge-token"?: string | null;
            };
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestoreArtifactRevisionRequest"];
            };
        };
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
    save_short_story_outline_api_v1_review_artifacts__artifact_id__outline_put: {
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
                "application/json": components["schemas"]["SaveShortStoryOutlineRequest"];
            };
        };
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
