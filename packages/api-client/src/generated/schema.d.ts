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
        /** ApproveVideoEpisodeScriptConfirmationRequest */
        ApproveVideoEpisodeScriptConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
            /** Confirmationhash */
            confirmationHash: string;
        };
        /** ApproveVideoStoryboardConfirmationRequest */
        ApproveVideoStoryboardConfirmationRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedartifactrevision */
            expectedArtifactRevision: number;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
            /** Confirmationhash */
            confirmationHash: string;
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
            /**
             * Engineversion
             * @default 1
             * @constant
             */
            engineVersion: 1;
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
        ArtifactDecisionPublicResponse: components["schemas"]["ArtifactDecisionAcceptedResponse"] | components["schemas"]["WritingRunV2Response"];
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
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "sfx" | "music";
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
        CancelWritingRunPublicResponse: components["schemas"]["CancelWritingRunResponse"] | components["schemas"]["WritingRunV2Response"];
        /** CancelWritingRunRequest */
        CancelWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
        };
        /** CancelWritingRunResponse */
        CancelWritingRunResponse: {
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
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
        /** ClarifyWritingRunRequest */
        ClarifyWritingRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Decisionstepid */
            decisionStepId: string;
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
        /** CreatePhoneChallengeRequest */
        CreatePhoneChallengeRequest: {
            /** Phone */
            phone: string;
            /** Captchaverifyparam */
            captchaVerifyParam: string;
            /** Consentversion */
            consentVersion: string;
            /**
             * Acceptedterms
             * @constant
             */
            acceptedTerms: true;
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
        /** CreateVideoEpisodeEditVersionRequest */
        CreateVideoEpisodeEditVersionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedheadrevision */
            expectedHeadRevision: number;
            /** Basedonversionid */
            basedOnVersionId?: string | null;
            /** Clips */
            clips: components["schemas"]["VideoEpisodeEditClipInput"][];
            /** Omissions */
            omissions?: components["schemas"]["VideoEpisodeShotOmissionInput"][];
        };
        /** CreateVideoEpisodeMixVersionRequest */
        CreateVideoEpisodeMixVersionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedheadrevision */
            expectedHeadRevision: number;
            /** Basedonversionid */
            basedOnVersionId?: string | null;
            /** Editversionid */
            editVersionId: string;
            /** Audioclips */
            audioClips?: components["schemas"]["VideoEpisodeAudioClipInput"][];
            /** Subtitlecues */
            subtitleCues?: components["schemas"]["VideoEpisodeSubtitleCueInput"][];
        };
        /** CreateVideoEpisodeRequest */
        CreateVideoEpisodeRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Title */
            title: string;
            /**
             * Creativeintent
             * @default
             */
            creativeIntent: string;
            /** Targetdurationseconds */
            targetDurationSeconds?: number | null;
        };
        /** CreateVideoEpisodeSourceSetRequest */
        CreateVideoEpisodeSourceSetRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Basedonversionid */
            basedOnVersionId?: string | null;
            /** Sources */
            sources: components["schemas"]["VideoEpisodeSourceSelection"][];
        };
        /** CreateVideoProductionBaselineRequest */
        CreateVideoProductionBaselineRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedepisoderevision */
            expectedEpisodeRevision: number;
            /** Expectedproductionrevision */
            expectedProductionRevision: number;
            /** Basedonbaselineid */
            basedOnBaselineId?: string | null;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Shotadoptions */
            shotAdoptions?: components["schemas"]["VideoProductionBaselineAdoptionInput"][];
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeInput"][];
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
        /** CreateVideoTakeAdoptionRequest */
        CreateVideoTakeAdoptionRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedproductionrevision */
            expectedProductionRevision: number;
            /** Targetshotversionid */
            targetShotVersionId: string;
            /** Sourcetakeid */
            sourceTakeId: string;
            /** Sourcebaselineid */
            sourceBaselineId: string;
            comparison: components["schemas"]["VideoTakeAdoptionComparison"];
        };
        /**
         * CreateVisualCanonCandidateRequest
         * @description 把已上传且已确认权利的图片放入一个视觉设定槽的候选位置。
         */
        CreateVisualCanonCandidateRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
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
        /** DecideVideoImpactReviewRequest */
        DecideVideoImpactReviewRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Decisions */
            decisions: components["schemas"]["VideoImpactDecision"][];
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
        /**
         * ModelProfileRef
         * @description Core 授权的逻辑模型 Profile；不包含 Agent 部署配置。
         */
        ModelProfileRef: {
            /** Profile */
            profile: string;
            /** Version */
            version: number;
            /**
             * Reasoningmode
             * @enum {string}
             */
            reasoningMode: "disabled" | "bounded";
            /** Deploymentprofilekey */
            deploymentProfileKey: string;
            promptProfile: components["schemas"]["PromptProfileRef"];
        };
        /** NaturalStartWritingRunRequest */
        NaturalStartWritingRunRequest: {
            /**
             * Inputmode
             * @constant
             */
            inputMode: "natural";
            /**
             * Workflow
             * @constant
             */
            workflow: "long_serial";
            /** Clientrequestid */
            clientRequestId: string;
            /** Novelid */
            novelId: string;
            /** Chapterid */
            chapterId: string;
            /** Writingsessionid */
            writingSessionId: string;
            /** Userinstruction */
            userInstruction: string;
            /**
             * Targetwordcount
             * @default 4000
             */
            targetWordCount: number;
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
            /** Id */
            id: string;
            /** Username */
            username: string;
            /** Creditbalancemicros */
            creditBalanceMicros: string;
            /** Maskedphone */
            maskedPhone: string;
            /** Isnewuser */
            isNewUser: boolean;
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
            /** Version */
            version: number;
            /** Sha256 */
            sha256: string;
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
        /** ReorderVideoEpisodesRequest */
        ReorderVideoEpisodesRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedprojectrevision */
            expectedProjectRevision: number;
            /** Episodeids */
            episodeIds: string[];
        };
        /**
         * ResolvedModelRef
         * @description Agent 对逻辑 Profile 的一次可审计部署解析。
         */
        ResolvedModelRef: {
            /** Deploymentprofilekey */
            deploymentProfileKey: string;
            /** Deploymentfingerprint */
            deploymentFingerprint: string;
            /** Provider */
            provider: string;
            /** Model */
            model: string;
            /** Transportprofile */
            transportProfile: string;
            /** Endpointprofile */
            endpointProfile: string;
            /**
             * Structuredoutputroute
             * @enum {string}
             */
            structuredOutputRoute: "responses_json_schema_v1" | "chat_json_output_v1" | "quality_strict_tool_v1" | "plain_text_v1" | "embeddings_v1";
            /** Capabilityversion */
            capabilityVersion: string;
            /**
             * Reasoningmode
             * @enum {string}
             */
            reasoningMode: "disabled" | "bounded";
            /**
             * Supportsrequestidempotency
             * @description 仅当 Provider 确实原样传递 ExecutionStepRequest.idempotencyKey 时为 true
             */
            supportsRequestIdempotency: boolean;
        } & ({
            /** @constant */
            structuredOutputRoute?: "embeddings_v1";
            model?: unknown;
        } | {
            /** @enum {unknown} */
            structuredOutputRoute?: "responses_json_schema_v1" | "chat_json_output_v1" | "quality_strict_tool_v1" | "plain_text_v1";
            model?: unknown;
        });
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
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string;
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
            /**
             * Engineversion
             * @description 审核决定引擎版本；省略只兼容解释为 V1，V2 必须显式提交 2
             * @default 1
             * @enum {integer}
             */
            engineVersion: 1 | 2;
            /** Clientrequestid */
            clientRequestId: string;
            /**
             * Expectedrevision
             * @description V1 为既有草案修订号；V2 为规范 expectedArtifactRevision wire 字段
             */
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
            /**
             * Engineversion
             * @enum {integer}
             */
            engineVersion: 1 | 2;
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
        /** ReviewArtifactSummaryListResponse */
        ReviewArtifactSummaryListResponse: {
            /** Items */
            items: components["schemas"]["ReviewArtifactSummaryResponse"][];
            /** Nextcursor */
            nextCursor: string | null;
        };
        /**
         * ReviewArtifactSummaryResponse
         * @description 集合查询使用的有界索引；完整内容必须按精确 revision 单独读取。
         */
        ReviewArtifactSummaryResponse: {
            /**
             * Engineversion
             * @enum {integer}
             */
            engineVersion: 1 | 2;
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
            /** Revision */
            revision: number;
            /** Actionable */
            actionable: boolean;
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
        /** SaveVideoEpisodeScriptDraftRequest */
        SaveVideoEpisodeScriptDraftRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Sourcesetversionid */
            sourceSetVersionId: string | null;
            /** Basescriptversionid */
            baseScriptVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
        };
        /** SaveVideoStoryboardDraftRequest */
        SaveVideoStoryboardDraftRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Basestoryboardversionid */
            baseStoryboardVersionId?: string | null;
            document: components["schemas"]["VideoStoryboardDocument"];
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
        /** StartVideoEpisodeExportRequest */
        StartVideoEpisodeExportRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Editversionid */
            editVersionId: string;
            /** Mixversionid */
            mixVersionId: string;
            /**
             * Resolution
             * @default 720p
             * @enum {string}
             */
            resolution: "720p" | "1080p";
            /**
             * Framespersecond
             * @default 24
             * @enum {integer}
             */
            framesPerSecond: 24 | 25 | 30;
            /**
             * Burnsubtitles
             * @default true
             */
            burnSubtitles: boolean;
        };
        /** StartVideoEpisodeScriptRunRequest */
        StartVideoEpisodeScriptRunRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /**
             * Operation
             * @enum {string}
             */
            operation: "episode_script_generate" | "episode_script_revise";
            /** Selectedsceneids */
            selectedSceneIds?: string[];
            /** Instruction */
            instruction: string;
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
            /** Scriptversionid */
            scriptVersionId: string;
            /**
             * Operation
             * @enum {string}
             */
            operation: "episode_storyboard_generate" | "episode_storyboard_revise";
            /** Selectedshotids */
            selectedShotIds?: string[];
            /** Instruction */
            instruction: string;
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
            /** Promptcachemisstokens */
            promptCacheMissTokens: number | null;
            /** Completiontokens */
            completionTokens: number;
            /** Reasoningtokens */
            reasoningTokens: number | null;
            /** Visiblecompletiontokens */
            visibleCompletionTokens: number | null;
            /** Tokendetailscomplete */
            tokenDetailsComplete: boolean;
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
            /** Promptcachemisstokens */
            promptCacheMissTokens: number | null;
            /** Completiontokens */
            completionTokens: number;
            /** Reasoningtokens */
            reasoningTokens: number | null;
            /** Visiblecompletiontokens */
            visibleCompletionTokens: number | null;
            /** Tokendetailscomplete */
            tokenDetailsComplete: boolean;
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
        /** UpdateVideoEpisodeRequest */
        UpdateVideoEpisodeRequest: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Expectedrevision */
            expectedRevision: number;
            /** Title */
            title?: string | null;
            /** Creativeintent */
            creativeIntent?: string | null;
            /** Targetdurationseconds */
            targetDurationSeconds?: number | null;
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
            /** Maskedphone */
            maskedPhone?: string | null;
        };
        /** VerifyPhoneChallengeRequest */
        VerifyPhoneChallengeRequest: {
            /** Phone */
            phone: string;
            /** Code */
            code: string;
            /** Clientrequestid */
            clientRequestId: string;
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
            duty: "identity" | "costume" | "scene" | "prop" | "style" | "storyboard" | "keyframe" | "motion" | "camera" | "voice" | "ambience" | "sfx" | "music" | "episode_export";
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
        /** VideoEpisodeAudioClipInput */
        VideoEpisodeAudioClipInput: {
            /**
             * Trackkind
             * @enum {string}
             */
            trackKind: "dialogue" | "narration" | "ambience" | "sfx" | "music";
            /** Assetid */
            assetId: string;
            /** Shotversionid */
            shotVersionId?: string | null;
            /** Timelinestartms */
            timelineStartMs: number;
            /**
             * Sourceinms
             * @default 0
             */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /**
             * Gainmillibels
             * @default 0
             */
            gainMillibels: number;
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
        };
        /** VideoEpisodeAudioClipResponse */
        VideoEpisodeAudioClipResponse: {
            /**
             * Trackkind
             * @enum {string}
             */
            trackKind: "dialogue" | "narration" | "ambience" | "sfx" | "music";
            /** Assetid */
            assetId: string;
            /** Shotversionid */
            shotVersionId?: string | null;
            /** Timelinestartms */
            timelineStartMs: number;
            /**
             * Sourceinms
             * @default 0
             */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /**
             * Gainmillibels
             * @default 0
             */
            gainMillibels: number;
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
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string | null;
            asset: components["schemas"]["VideoEpisodePostAssetResponse"];
        };
        /** VideoEpisodeCommandResponse */
        VideoEpisodeCommandResponse: {
            /** Clientrequestid */
            clientRequestId: string;
            /** Episodeid */
            episodeId: string | null;
            /** Operation */
            operation: string;
            /**
             * Resulttype
             * @enum {string}
             */
            resultType: "episode" | "episode_list" | "source_set" | "script_draft" | "script_confirmation" | "script_version" | "script_run" | "storyboard_draft" | "storyboard_confirmation" | "storyboard_version" | "storyboard_run" | "take_adoption" | "production_baseline";
            /** Resultid */
            resultId: string;
            /** Resultrevision */
            resultRevision: number | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodeDeliveryAssetResponse */
        VideoEpisodeDeliveryAssetResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Modality
             * @constant
             */
            modality: "video";
            /** Mimetype */
            mimeType: string;
            /** Durationms */
            durationMs: number;
            /** Bytesize */
            byteSize: number;
            /** Sha256 */
            sha256: string;
            /** Contenturl */
            contentUrl: string;
        };
        /** VideoEpisodeDeliveryResponse */
        VideoEpisodeDeliveryResponse: {
            /** Id */
            id: string;
            /** Taskid */
            taskId: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Versionno */
            versionNo: number;
            /** Editversionid */
            editVersionId: string;
            /** Mixversionid */
            mixVersionId: string;
            /** Inputhash */
            inputHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            asset: components["schemas"]["VideoEpisodeDeliveryAssetResponse"];
        };
        /** VideoEpisodeDependencyInput */
        VideoEpisodeDependencyInput: {
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerscriptversionid */
            producerScriptVersionId: string;
            /** Producerstatekey */
            producerStateKey: string;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Consumerlineid */
            consumerLineId?: string | null;
            /** Narrativetime */
            narrativeTime: string;
            /** Description */
            description: string;
        };
        /** VideoEpisodeDependencyResponse */
        VideoEpisodeDependencyResponse: {
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Producerscriptversionid */
            producerScriptVersionId: string;
            /** Producerstatekey */
            producerStateKey: string;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Consumerlineid */
            consumerLineId?: string | null;
            /** Narrativetime */
            narrativeTime: string;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Consumerepisodeid */
            consumerEpisodeId: string;
            /** Consumerscriptversionid */
            consumerScriptVersionId: string;
            /** Producerstatehash */
            producerStateHash: string;
        };
        /** VideoEpisodeDetailResponse */
        VideoEpisodeDetailResponse: {
            episode: components["schemas"]["VideoEpisodeResponse"];
            /** Sourcesets */
            sourceSets: components["schemas"]["VideoEpisodeSourceSetResponse"][];
            scriptDraft: components["schemas"]["VideoEpisodeScriptDraftResponse"];
            currentScriptVersion: components["schemas"]["VideoEpisodeScriptVersionResponse"] | null;
            /** Scriptversions */
            scriptVersions: components["schemas"]["VideoEpisodeScriptVersionResponse"][];
            /** Candidateartifacts */
            candidateArtifacts: components["schemas"]["VideoEpisodeScriptCandidateResponse"][];
            latestScriptRun?: components["schemas"]["VideoEpisodeScriptRunResponse"] | null;
            /** Dependencies */
            dependencies: components["schemas"]["VideoEpisodeDependencyResponse"][];
        };
        /** VideoEpisodeEditClipInput */
        VideoEpisodeEditClipInput: {
            /** Tempkey */
            tempKey: string;
            /** Adoptionid */
            adoptionId: string;
            /** Takeid */
            takeId: string;
            /** Sourceinms */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /**
             * Sourceaudiomode
             * @enum {string}
             */
            sourceAudioMode: "keep" | "mute";
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
            /** Clipid */
            clipId: string;
            /** Ordinal */
            ordinal: number;
            /** Adoptionid */
            adoptionId: string;
            /** Takeid */
            takeId: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Sourceinms */
            sourceInMs: number;
            /** Sourceoutms */
            sourceOutMs: number;
            /** Timelinestartms */
            timelineStartMs: number;
            /** Outputdurationms */
            outputDurationMs: number;
            /**
             * Sourceaudiomode
             * @enum {string}
             */
            sourceAudioMode: "keep" | "mute";
            /**
             * Transitionafter
             * @enum {string}
             */
            transitionAfter: "cut" | "fade_black";
            /** Transitiondurationms */
            transitionDurationMs: number;
            asset: components["schemas"]["VideoEpisodePostAssetResponse"];
        };
        /** VideoEpisodeEditVersionListResponse */
        VideoEpisodeEditVersionListResponse: {
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Headrevision */
            headRevision: number;
            /** Currentversionid */
            currentVersionId: string | null;
            /** Versions */
            versions: components["schemas"]["VideoEpisodeEditVersionSummary"][];
            /** Nextbeforeversionno */
            nextBeforeVersionNo: number | null;
        };
        /** VideoEpisodeEditVersionResponse */
        VideoEpisodeEditVersionResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Clipcount */
            clipCount: number;
            /** Omissioncount */
            omissionCount: number;
            /** Totaldurationms */
            totalDurationMs: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Clips */
            clips: components["schemas"]["VideoEpisodeEditClipResponse"][];
            /** Omissions */
            omissions: components["schemas"]["VideoEpisodeShotOmissionResponse"][];
            /** Headrevision */
            headRevision: number;
        };
        /** VideoEpisodeEditVersionSummary */
        VideoEpisodeEditVersionSummary: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Clipcount */
            clipCount: number;
            /** Omissioncount */
            omissionCount: number;
            /** Totaldurationms */
            totalDurationMs: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodeEndingState */
        VideoEpisodeEndingState: {
            /** Key */
            key: string;
            /** Description */
            description: string;
            /** Entityids */
            entityIds?: string[];
            /**
             * Narrativetime
             * @default
             */
            narrativeTime: string;
        };
        /** VideoEpisodeExportTaskResponse */
        VideoEpisodeExportTaskResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Editversionid */
            editVersionId: string;
            /** Mixversionid */
            mixVersionId: string;
            /** Retryoftaskid */
            retryOfTaskId: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "rendering" | "succeeded" | "failed";
            /** Clientrequestid */
            clientRequestId: string;
            /** Inputhash */
            inputHash: string;
            /**
             * Resolution
             * @enum {string}
             */
            resolution: "720p" | "1080p";
            /**
             * Framespersecond
             * @enum {integer}
             */
            framesPerSecond: 24 | 25 | 30;
            /** Burnsubtitles */
            burnSubtitles: boolean;
            /** Attemptcount */
            attemptCount: number;
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
            /** Startedat */
            startedAt: string | null;
            /** Completedat */
            completedAt: string | null;
            export: components["schemas"]["VideoEpisodeDeliveryResponse"] | null;
        };
        /** VideoEpisodeListResponse */
        VideoEpisodeListResponse: {
            /** Projectid */
            projectId: string;
            /** Projectrevision */
            projectRevision: number;
            /** Episodes */
            episodes: components["schemas"]["VideoEpisodeResponse"][];
        };
        /** VideoEpisodeMixVersionListResponse */
        VideoEpisodeMixVersionListResponse: {
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Headrevision */
            headRevision: number;
            /** Currentversionid */
            currentVersionId: string | null;
            /** Versions */
            versions: components["schemas"]["VideoEpisodeMixVersionSummary"][];
            /** Nextbeforeversionno */
            nextBeforeVersionNo: number | null;
        };
        /** VideoEpisodeMixVersionResponse */
        VideoEpisodeMixVersionResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Editversionid */
            editVersionId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Audioclipcount */
            audioClipCount: number;
            /** Subtitlecuecount */
            subtitleCueCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Audioclips */
            audioClips: components["schemas"]["VideoEpisodeAudioClipResponse"][];
            /** Subtitlecues */
            subtitleCues: components["schemas"]["VideoEpisodeSubtitleCueResponse"][];
            /** Headrevision */
            headRevision: number;
        };
        /** VideoEpisodeMixVersionSummary */
        VideoEpisodeMixVersionSummary: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Editversionid */
            editVersionId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Audioclipcount */
            audioClipCount: number;
            /** Subtitlecuecount */
            subtitleCueCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodePostAssetResponse */
        VideoEpisodePostAssetResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Modality
             * @enum {string}
             */
            modality: "video" | "audio";
            /** Mimetype */
            mimeType: string;
            /** Durationms */
            durationMs: number;
            /** Bytesize */
            byteSize: number;
            /** Sha256 */
            sha256: string;
        };
        /**
         * VideoEpisodeProductionShotInput
         * @description 制作基线逐镜冻结输入；渲染任务不得从可变 Head 重新拼装。
         */
        VideoEpisodeProductionShotInput: {
            /**
             * Schemaversion
             * @enum {string}
             */
            schemaVersion: "video-production-shot-input/1.0" | "video-production-shot-input/1.1" | "video-production-shot-input/1.2";
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Shotversionno */
            shotVersionNo: number;
            /** Shotcontenthash */
            shotContentHash: string;
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Scriptlineids */
            scriptLineIds?: string[];
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /** Promptversionid */
            promptVersionId: string;
            /** Prompt */
            prompt: string;
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Resolution
             * @constant
             */
            resolution: "720p";
            /** Generateaudio */
            generateAudio: boolean;
            /** Watermark */
            watermark: boolean;
            /**
             * Outputformat
             * @constant
             */
            outputFormat: "mp4";
            /** References */
            references: components["schemas"]["VideoEpisodeRenderReference"][];
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeSnapshot"][];
        };
        /** VideoEpisodeRenderReference */
        VideoEpisodeRenderReference: {
            /** Ordinal */
            ordinal: number;
            /** Canonversionid */
            canonVersionId: string;
            /** Canoncontenthash */
            canonContentHash: string;
            /** Assetid */
            assetId: string;
            /** Sha256 */
            sha256: string;
            /**
             * Mimetype
             * @enum {string}
             */
            mimeType: "image/jpeg" | "image/png" | "image/webp";
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop";
            /** Rightsstatus */
            rightsStatus?: "confirmed" | null;
            /** Lockedat */
            lockedAt?: string | null;
            /** Strength */
            strength: number;
        };
        /** VideoEpisodeRenderTaskResponse */
        VideoEpisodeRenderTaskResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Productionbaselineid */
            productionBaselineId: string;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Promptversionid */
            promptVersionId: string;
            /** Retryoftaskid */
            retryOfTaskId: string | null;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "submitting" | "submission_unknown" | "queued" | "running" | "archiving" | "succeeded" | "failed" | "expired" | "cancelled";
            /** Inputhash */
            inputHash: string;
            inputSnapshot: components["schemas"]["VideoEpisodeProductionShotInput"];
            /** Providertaskid */
            providerTaskId: string | null;
            /** Pollcount */
            pollCount: number;
            /** Attemptcount */
            attemptCount: number;
            /** Lasterrorcode */
            lastErrorCode: string | null;
            /** Lasterrormessage */
            lastErrorMessage: string | null;
            /** Takeid */
            takeId: string | null;
            /** Mediakind */
            mediaKind: ("provider_media" | "simulated_placeholder") | null;
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
            /** Submittedat */
            submittedAt: string | null;
            /** Completedat */
            completedAt: string | null;
        };
        /** VideoEpisodeResponse */
        VideoEpisodeResponse: {
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Novelid */
            novelId: string;
            /** Title */
            title: string;
            /** Creativeintent */
            creativeIntent: string;
            /** Targetdurationseconds */
            targetDurationSeconds: number | null;
            /** Order */
            order: number;
            /** Revision */
            revision: number;
            /** Currentsourcesetversionid */
            currentSourceSetVersionId: string | null;
            /** Currentscriptversionid */
            currentScriptVersionId: string | null;
            /** Currentstoryboardversionid */
            currentStoryboardVersionId: string | null;
            /** Currentproductionbaselineid */
            currentProductionBaselineId: string | null;
            /** Productionrevision */
            productionRevision: number;
            /** Latestdeliveryversionid */
            latestDeliveryVersionId: string | null;
            /** Deliveryrevision */
            deliveryRevision: number;
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
        /** VideoEpisodeScriptCandidateResponse */
        VideoEpisodeScriptCandidateResponse: {
            /** Artifactid */
            artifactId: string;
            /** Workflowrunid */
            workflowRunId: string;
            /** Episodeid */
            episodeId: string;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "awaiting_user" | "applied" | "rejected";
            /** Title */
            title: string;
            /** Summary */
            summary: string | null;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Sourcesetversionid */
            sourceSetVersionId: string | null;
            /** Basescriptversionid */
            baseScriptVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Reviewfindings */
            reviewFindings?: components["schemas"]["VideoEpisodeScriptReviewFinding"][];
            review?: components["schemas"]["VideoEpisodeScriptReview"] | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodeScriptConfirmationResponse */
        VideoEpisodeScriptConfirmationResponse: {
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            /** Episodeid */
            episodeId: string;
            /** Episoderevision */
            episodeRevision: number;
            /** Draftrevision */
            draftRevision: number;
            /** Sourcesetversionid */
            sourceSetVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Confirmationhash */
            confirmationHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /**
         * VideoEpisodeScriptDocument
         * @description 工作稿和正式版共用完整结构；空工作稿不冒充已经确认的剧本。
         */
        VideoEpisodeScriptDocument: {
            /**
             * Schemaversion
             * @default video-episode-script/1.0
             * @constant
             */
            schemaVersion: "video-episode-script/1.0";
            overview?: components["schemas"]["VideoEpisodeScriptOverview"];
            /** Scenes */
            scenes?: components["schemas"]["VideoEpisodeScriptScene"][];
            /** Endingstates */
            endingStates?: components["schemas"]["VideoEpisodeEndingState"][];
            /** Dependencies */
            dependencies?: components["schemas"]["VideoEpisodeDependencyInput"][];
        };
        /** VideoEpisodeScriptDraftResponse */
        VideoEpisodeScriptDraftResponse: {
            /** Episodeid */
            episodeId: string;
            /** Revision */
            revision: number;
            /** Sourcesetversionid */
            sourceSetVersionId: string | null;
            /** Basescriptversionid */
            baseScriptVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Adoptedartifactid */
            adoptedArtifactId: string | null;
            /** Nodeidmappings */
            nodeIdMappings?: {
                [key: string]: string;
            };
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
        };
        /** VideoEpisodeScriptLine */
        VideoEpisodeScriptLine: {
            /** Id */
            id?: string | null;
            /** Tempkey */
            tempKey?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "action" | "dialogue" | "narration";
            /** Speakerid */
            speakerId?: string | null;
            /** Text */
            text: string;
            /** Sourcerefs */
            sourceRefs?: components["schemas"]["VideoEpisodeSourceRef"][];
        };
        /** VideoEpisodeScriptOverview */
        VideoEpisodeScriptOverview: {
            /**
             * Summary
             * @default
             */
            summary: string;
            /**
             * Creativeintent
             * @default
             */
            creativeIntent: string;
            /** Targetdurationseconds */
            targetDurationSeconds?: number | null;
        };
        /** VideoEpisodeScriptReview */
        VideoEpisodeScriptReview: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "pass" | "revise";
            /** Summary */
            summary: string;
            /** Requiredchanges */
            requiredChanges: string[];
            /** Findings */
            findings: components["schemas"]["VideoEpisodeScriptReviewFinding"][];
        };
        /** VideoEpisodeScriptReviewFinding */
        VideoEpisodeScriptReviewFinding: {
            /**
             * Code
             * @enum {string}
             */
            code: "source" | "continuity" | "dialogue" | "clarity";
            /** Sceneid */
            sceneId: string | null;
            /** Lineid */
            lineId: string | null;
            /** Message */
            message: string;
        };
        /** VideoEpisodeScriptRunResponse */
        VideoEpisodeScriptRunResponse: {
            /** Runid */
            runId: string;
            /** Episodeid */
            episodeId: string;
            /** Status */
            status: string;
            /** Artifactid */
            artifactId: string | null;
            /** Errorcode */
            errorCode: string | null;
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
        /** VideoEpisodeScriptScene */
        VideoEpisodeScriptScene: {
            /** Id */
            id?: string | null;
            /** Tempkey */
            tempKey?: string | null;
            /** Title */
            title: string;
            /** Locationlabel */
            locationLabel: string;
            /** Timelabel */
            timeLabel: string;
            /** Narrativetime */
            narrativeTime: string;
            /** Characterids */
            characterIds?: string[];
            /** Lines */
            lines?: components["schemas"]["VideoEpisodeScriptLine"][];
        };
        /** VideoEpisodeScriptVersionListResponse */
        VideoEpisodeScriptVersionListResponse: {
            /** Versions */
            versions: components["schemas"]["VideoEpisodeScriptVersionResponse"][];
        };
        /** VideoEpisodeScriptVersionResponse */
        VideoEpisodeScriptVersionResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Sourcesetversionid */
            sourceSetVersionId: string | null;
            document: components["schemas"]["VideoEpisodeScriptDocument"];
            /** Contenthash */
            contentHash: string;
            /** Confirmationartifactid */
            confirmationArtifactId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodeShotOmissionInput */
        VideoEpisodeShotOmissionInput: {
            /** Shotversionid */
            shotVersionId: string;
            /** Reason */
            reason: string;
        };
        /** VideoEpisodeShotOmissionResponse */
        VideoEpisodeShotOmissionResponse: {
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Reason */
            reason: string;
        };
        /** VideoEpisodeSourceRange */
        VideoEpisodeSourceRange: {
            /** Start */
            start: number;
            /** End */
            end: number;
        };
        /** VideoEpisodeSourceRef */
        VideoEpisodeSourceRef: {
            /** Sourcesnapshotid */
            sourceSnapshotId: string;
            /** Start */
            start: number;
            /** End */
            end: number;
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
            /** Sourcehash */
            sourceHash: string;
            /** Ranges */
            ranges: components["schemas"]["VideoEpisodeSourceRange"][];
        };
        /** VideoEpisodeSourceSetListResponse */
        VideoEpisodeSourceSetListResponse: {
            /** Sourcesets */
            sourceSets: components["schemas"]["VideoEpisodeSourceSetResponse"][];
        };
        /** VideoEpisodeSourceSetResponse */
        VideoEpisodeSourceSetResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Contenthash */
            contentHash: string;
            /** Sources */
            sources: components["schemas"]["VideoEpisodeSourceSnapshotResponse"][];
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoEpisodeSourceSnapshotResponse */
        VideoEpisodeSourceSnapshotResponse: {
            /** Id */
            id: string;
            /** Chapterid */
            chapterId: string;
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
            /** Ranges */
            ranges: components["schemas"]["VideoEpisodeSourceRange"][];
            /**
             * Sourcestatus
             * @default unknown
             * @enum {string}
             */
            sourceStatus: "current" | "updated" | "missing" | "unknown";
            /** Currentchapterupdatedat */
            currentChapterUpdatedAt?: string | null;
            /** Currentchaptercontenthash */
            currentChapterContentHash?: string | null;
        };
        /** VideoEpisodeSubtitleCueInput */
        VideoEpisodeSubtitleCueInput: {
            /** Shotversionid */
            shotVersionId: string;
            /** Scriptlineid */
            scriptLineId: string;
            /** Startms */
            startMs: number;
            /** Endms */
            endMs: number;
            /** Speaker */
            speaker?: string | null;
            /** Text */
            text: string;
        };
        /** VideoEpisodeSubtitleCueResponse */
        VideoEpisodeSubtitleCueResponse: {
            /** Shotversionid */
            shotVersionId: string;
            /** Scriptlineid */
            scriptLineId: string;
            /** Startms */
            startMs: number;
            /** Endms */
            endMs: number;
            /** Speaker */
            speaker?: string | null;
            /** Text */
            text: string;
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string;
        };
        /** VideoImpactDecision */
        VideoImpactDecision: {
            /** Itemid */
            itemId: string;
            /**
             * Action
             * @enum {string}
             */
            action: "keep_existing" | "revise_target" | "not_applicable" | "defer";
            /**
             * Note
             * @default
             */
            note: string;
        };
        /** VideoImpactReviewItem */
        VideoImpactReviewItem: {
            /** Itemid */
            itemId: string;
            /** Dependencyid */
            dependencyId: string;
            /**
             * Kind
             * @constant
             */
            kind: "direct_dependency_changed";
            /**
             * Changetype
             * @enum {string}
             */
            changeType: "changed" | "removed";
            /** Producerstatekey */
            producerStateKey: string;
            beforeState: components["schemas"]["VideoImpactStateSnapshot"];
            afterState: components["schemas"]["VideoImpactStateSnapshot"] | null;
            /** Consumersceneid */
            consumerSceneId: string;
            /** Consumerlineid */
            consumerLineId: string | null;
            /** Narrativetime */
            narrativeTime: string;
            /** Description */
            description: string;
            /** Beforestatehash */
            beforeStateHash: string;
            /** Afterstatehash */
            afterStateHash?: string | null;
            /** Itemhash */
            itemHash: string;
        };
        /** VideoImpactReviewListResponse */
        VideoImpactReviewListResponse: {
            /** Reviews */
            reviews: components["schemas"]["VideoImpactReviewSummaryResponse"][];
            /** Nextbeforereviewid */
            nextBeforeReviewId: string | null;
        };
        /** VideoImpactReviewReport */
        VideoImpactReviewReport: {
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "video-impact-review/1.0";
            /**
             * Kind
             * @constant
             */
            kind: "explicit_dependency_changed";
            /**
             * Requiresauthorreview
             * @constant
             */
            requiresAuthorReview: true;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Producerbaselineid */
            producerBaselineId: string | null;
            /** Targetbaselineid */
            targetBaselineId: string | null;
            /** Items */
            items: components["schemas"]["VideoImpactReviewItem"][];
        };
        /** VideoImpactReviewResponse */
        VideoImpactReviewResponse: {
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Producerbaselineid */
            producerBaselineId: string | null;
            /** Targetbaselineid */
            targetBaselineId: string | null;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "resolved";
            /** Itemcount */
            itemCount: number;
            /** Decisioncount */
            decisionCount: number;
            /** Isstale */
            isStale: boolean;
            /** Stalereasons */
            staleReasons: string[];
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
            report: components["schemas"]["VideoImpactReviewReport"];
            /** Decisions */
            decisions: components["schemas"]["VideoImpactDecision"][];
        };
        /** VideoImpactReviewSummaryResponse */
        VideoImpactReviewSummaryResponse: {
            /** Id */
            id: string;
            /** Projectid */
            projectId: string;
            /** Producerepisodeid */
            producerEpisodeId: string;
            /** Beforescriptversionid */
            beforeScriptVersionId: string;
            /** Afterscriptversionid */
            afterScriptVersionId: string;
            /** Targetepisodeid */
            targetEpisodeId: string;
            /** Targetscriptversionid */
            targetScriptVersionId: string;
            /** Producerproductionrevision */
            producerProductionRevision: number;
            /** Targetproductionrevision */
            targetProductionRevision: number;
            /** Producerbaselineid */
            producerBaselineId: string | null;
            /** Targetbaselineid */
            targetBaselineId: string | null;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "resolved";
            /** Itemcount */
            itemCount: number;
            /** Decisioncount */
            decisionCount: number;
            /** Isstale */
            isStale: boolean;
            /** Stalereasons */
            staleReasons: string[];
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
        /** VideoImpactStateSnapshot */
        VideoImpactStateSnapshot: {
            /** Key */
            key: string;
            /** Description */
            description: string;
            /** Narrativetime */
            narrativeTime: string;
            /** Entityids */
            entityIds?: string[];
        };
        /** VideoProductionBaselineAdoptionInput */
        VideoProductionBaselineAdoptionInput: {
            /** Shotversionid */
            shotVersionId: string;
            /** Adoptionid */
            adoptionId: string;
        };
        /** VideoProductionBaselineListResponse */
        VideoProductionBaselineListResponse: {
            /** Baselines */
            baselines: components["schemas"]["VideoProductionBaselineSummary"][];
            /** Nextbeforeversionno */
            nextBeforeVersionNo: number | null;
        };
        /** VideoProductionBaselineManifest */
        VideoProductionBaselineManifest: {
            /**
             * Schemaversion
             * @constant
             */
            schemaVersion: "video-production-baseline/1.0";
            /** Episodeid */
            episodeId: string;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Shots */
            shots: components["schemas"]["VideoProductionBaselineManifestShot"][];
        };
        /** VideoProductionBaselineManifestShot */
        VideoProductionBaselineManifestShot: {
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Adoptionid */
            adoptionId: string | null;
            /** Inputhash */
            inputHash: string;
        };
        /** VideoProductionBaselineResponse */
        VideoProductionBaselineResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonbaselineid */
            basedOnBaselineId: string | null;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            manifest: components["schemas"]["VideoProductionBaselineManifest"];
            /** Shots */
            shots: components["schemas"]["VideoProductionBaselineShotResponse"][];
            /** Productionrevision */
            productionRevision: number;
        };
        /** VideoProductionBaselineShotResponse */
        VideoProductionBaselineShotResponse: {
            /** Ordinal */
            ordinal: number;
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Adoptionid */
            adoptionId: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "adopted";
            inputSnapshot: components["schemas"]["VideoProductionShotInputSnapshot"];
            /** Inputhash */
            inputHash: string;
        };
        /** VideoProductionBaselineSummary */
        VideoProductionBaselineSummary: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonbaselineid */
            basedOnBaselineId: string | null;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoProductionCapabilityResponse */
        VideoProductionCapabilityResponse: {
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmationrequired */
            feeConfirmationRequired: boolean;
            /** Videopreviewenabled */
            videoPreviewEnabled: boolean;
            /** Providerconfigured */
            providerConfigured: boolean;
            /** Providerenabled */
            providerEnabled: boolean;
            /** Alloweddurationseconds */
            allowedDurationSeconds: number[];
            /**
             * Allowedresolution
             * @constant
             */
            allowedResolution: "720p";
            /**
             * Allowedoutputformat
             * @constant
             */
            allowedOutputFormat: "mp4";
            /**
             * Maximagereferences
             * @constant
             */
            maxImageReferences: 20;
        };
        /** VideoProductionKeyframeInput */
        VideoProductionKeyframeInput: {
            /** Shotversionid */
            shotVersionId: string;
            /**
             * Role
             * @enum {string}
             */
            role: "initial_state" | "transition_anchor" | "end_state";
            /** Assetid */
            assetId: string;
        };
        /** VideoProductionKeyframeSnapshot */
        VideoProductionKeyframeSnapshot: {
            /** Ordinal */
            ordinal: number;
            /** Keyframeversionid */
            keyframeVersionId: string;
            /**
             * Role
             * @enum {string}
             */
            role: "initial_state" | "transition_anchor" | "end_state";
            /** Assetid */
            assetId: string;
            /** Sha256 */
            sha256: string;
            /**
             * Mimetype
             * @enum {string}
             */
            mimeType: "image/jpeg" | "image/png" | "image/webp";
            /**
             * Duty
             * @enum {string}
             */
            duty: "identity" | "costume" | "scene" | "prop" | "storyboard" | "keyframe";
            /** Rightsstatus */
            rightsStatus?: "confirmed" | null;
            /** Lockedat */
            lockedAt?: string | null;
            /** Contenthash */
            contentHash: string;
        };
        /** VideoProductionShotInputSnapshot */
        VideoProductionShotInputSnapshot: {
            /**
             * Schemaversion
             * @enum {string}
             */
            schemaVersion: "video-production-shot-input/1.0" | "video-production-shot-input/1.1" | "video-production-shot-input/1.2";
            /** Shotid */
            shotId: string;
            /** Shotversionid */
            shotVersionId: string;
            /** Shotversionno */
            shotVersionNo: number;
            /** Shotcontenthash */
            shotContentHash: string;
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Scriptlineids */
            scriptLineIds: string[];
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /**
             * Generationmode
             * @constant
             */
            generationMode: "reference";
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /** Promptversionid */
            promptVersionId: string;
            /** Prompt */
            prompt: string;
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Resolution
             * @constant
             */
            resolution: "720p";
            /** Generateaudio */
            generateAudio: boolean;
            /** Watermark */
            watermark: boolean;
            /**
             * Outputformat
             * @constant
             */
            outputFormat: "mp4";
            /** References */
            references: components["schemas"]["VideoShotReferenceInput"][];
            /** Keyframes */
            keyframes?: components["schemas"]["VideoProductionKeyframeSnapshot"][];
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
        /** VideoShotLineageInput */
        VideoShotLineageInput: {
            /** Sourceshotid */
            sourceShotId: string;
            /**
             * Relation
             * @enum {string}
             */
            relation: "replacement" | "copy" | "split" | "merge";
        };
        /** VideoShotProductionIntent */
        VideoShotProductionIntent: {
            /**
             * Provider
             * @default seedance
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /**
             * Generationmode
             * @default reference
             * @constant
             */
            generationMode: "reference";
            /**
             * Executionmode
             * @enum {string}
             */
            executionMode: "simulated" | "live";
            /** Feeconfirmed */
            feeConfirmed: boolean;
            /** Prompt */
            prompt: string;
            /**
             * Ratio
             * @enum {string}
             */
            ratio: "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive";
            /** Durationseconds */
            durationSeconds: number;
            /**
             * Resolution
             * @default 720p
             * @constant
             */
            resolution: "720p";
            /**
             * Generateaudio
             * @default true
             */
            generateAudio: boolean;
            /**
             * Watermark
             * @default false
             */
            watermark: boolean;
            /**
             * Outputformat
             * @default mp4
             * @constant
             */
            outputFormat: "mp4";
            /** References */
            references: components["schemas"]["VideoShotReferenceInput"][];
        };
        /** VideoShotReferenceInput */
        VideoShotReferenceInput: {
            /** Canonversionid */
            canonVersionId: string;
            /** Strength */
            strength?: number | null;
            /** Ordinal */
            ordinal?: number | null;
            /** Canoncontenthash */
            canonContentHash?: string | null;
            /** Assetid */
            assetId?: string | null;
            /** Sha256 */
            sha256?: string | null;
            /** Mimetype */
            mimeType?: ("image/jpeg" | "image/png" | "image/webp") | null;
            /** Duty */
            duty?: ("identity" | "costume" | "scene" | "prop") | null;
            /** Rightsstatus */
            rightsStatus?: "confirmed" | null;
            /** Lockedat */
            lockedAt?: string | null;
        };
        /** VideoShotVersionResponse */
        VideoShotVersionResponse: {
            /** Id */
            id: string;
            /** Shotid */
            shotId: string;
            /** Storyboardversionid */
            storyboardVersionId: string;
            /** Ordinal */
            ordinal: number;
            /** Versionno */
            versionNo: number;
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Scriptlineids */
            scriptLineIds: string[];
            content: components["schemas"]["VideoStoryboardShot"];
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoStoryboardCandidateResponse */
        VideoStoryboardCandidateResponse: {
            /** Artifactid */
            artifactId: string;
            /** Workflowrunid */
            workflowRunId: string;
            /** Episodeid */
            episodeId: string;
            /** Revision */
            revision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "awaiting_user" | "applied" | "rejected";
            /** Title */
            title: string;
            /** Summary */
            summary: string | null;
            /** Expecteddraftrevision */
            expectedDraftRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Basestoryboardversionid */
            baseStoryboardVersionId: string | null;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Reviewfindings */
            reviewFindings?: components["schemas"]["VideoStoryboardReviewFinding"][];
            review?: components["schemas"]["VideoStoryboardReview"] | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoStoryboardConfirmationResponse */
        VideoStoryboardConfirmationResponse: {
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            /** Episodeid */
            episodeId: string;
            /** Episoderevision */
            episodeRevision: number;
            /** Draftrevision */
            draftRevision: number;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Basestoryboardversionid */
            baseStoryboardVersionId: string | null;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Confirmationhash */
            confirmationHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
            /** Episodeid */
            episodeId: string;
            /** Revision */
            revision: number;
            /** Scriptversionid */
            scriptVersionId: string | null;
            /** Basestoryboardversionid */
            baseStoryboardVersionId: string | null;
            document: components["schemas"]["VideoStoryboardDocument"];
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
            /** Summary */
            summary: string;
            /** Requiredchanges */
            requiredChanges: string[];
            /** Findings */
            findings: components["schemas"]["VideoStoryboardReviewFinding"][];
        };
        /** VideoStoryboardReviewFinding */
        VideoStoryboardReviewFinding: {
            /**
             * Code
             * @enum {string}
             */
            code: "script_coverage" | "continuity" | "shot_clarity" | "feasibility" | "reference" | "duration";
            /** Shotid */
            shotId: string | null;
            /** Scriptsceneid */
            scriptSceneId: string | null;
            /** Message */
            message: string;
        };
        /** VideoStoryboardRunListResponse */
        VideoStoryboardRunListResponse: {
            /** Runs */
            runs: components["schemas"]["VideoStoryboardRunResponse"][];
            /** Nextbeforerunid */
            nextBeforeRunId: string | null;
        };
        /** VideoStoryboardRunResponse */
        VideoStoryboardRunResponse: {
            /** Runid */
            runId: string;
            /** Episodeid */
            episodeId: string;
            /** Status */
            status: string;
            /** Artifactid */
            artifactId: string | null;
            /** Errorcode */
            errorCode: string | null;
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
        /** VideoStoryboardShot */
        VideoStoryboardShot: {
            /** Id */
            id?: string | null;
            /** Tempkey */
            tempKey?: string | null;
            /** Lineage */
            lineage?: components["schemas"]["VideoShotLineageInput"][];
            /** Scriptsceneid */
            scriptSceneId: string;
            /** Scriptlineids */
            scriptLineIds?: string[];
            /** Title */
            title: string;
            /** Action */
            action: string;
            /**
             * Framing
             * @enum {string}
             */
            framing: "extreme_wide" | "wide" | "medium" | "close_up" | "detail" | "over_shoulder" | "pov";
            /**
             * Cameramovement
             * @enum {string}
             */
            cameraMovement: "static" | "pan" | "tilt" | "dolly" | "truck" | "crane" | "handheld" | "orbit" | "zoom";
            /** Durationms */
            durationMs: number;
            productionIntent: components["schemas"]["VideoShotProductionIntent"];
        };
        /** VideoStoryboardVersionListResponse */
        VideoStoryboardVersionListResponse: {
            /** Versions */
            versions: components["schemas"]["VideoStoryboardVersionSummary"][];
            /** Nextbeforeversionno */
            nextBeforeVersionNo: number | null;
        };
        /** VideoStoryboardVersionResponse */
        VideoStoryboardVersionResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            document: components["schemas"]["VideoStoryboardDocument"];
            /** Shots */
            shots: components["schemas"]["VideoShotVersionResponse"][];
            /** Confirmationartifactid */
            confirmationArtifactId: string;
        };
        /** VideoStoryboardVersionSummary */
        VideoStoryboardVersionSummary: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Versionno */
            versionNo: number;
            /** Basedonversionid */
            basedOnVersionId: string | null;
            /** Scriptversionid */
            scriptVersionId: string;
            /** Shotcount */
            shotCount: number;
            /** Contenthash */
            contentHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoTakeAdoptionComparison */
        VideoTakeAdoptionComparison: {
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
            /** Directinputsunchanged */
            directInputsUnchanged: boolean;
            /** Referencehasheschecked */
            referenceHashesChecked?: string[];
            /** Summary */
            summary: string;
        };
        /** VideoTakeAdoptionResponse */
        VideoTakeAdoptionResponse: {
            /** Id */
            id: string;
            /** Episodeid */
            episodeId: string;
            /** Targetshotid */
            targetShotId: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
            /** Sourcetakeid */
            sourceTakeId: string;
            /** Sourcebaselineid */
            sourceBaselineId: string;
            comparison: components["schemas"]["VideoTakeAdoptionComparison"];
            /** Decisionhash */
            decisionHash: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
        };
        /** VideoTakeCandidateListResponse */
        VideoTakeCandidateListResponse: {
            /** Episodeid */
            episodeId: string;
            /** Targetshotversionid */
            targetShotVersionId: string;
            /** Takes */
            takes: components["schemas"]["VideoTakeCandidateSummary"][];
            /** Nextbeforetakeid */
            nextBeforeTakeId: string | null;
        };
        /** VideoTakeCandidateSummary */
        VideoTakeCandidateSummary: {
            /** Id */
            id: string;
            /** Takeno */
            takeNo: number;
            /** Sourcebaselineid */
            sourceBaselineId: string;
            /** Sourceshotid */
            sourceShotId: string;
            /** Sourceshotversionid */
            sourceShotVersionId: string;
            /** Promptversionid */
            promptVersionId: string;
            /** Assetid */
            assetId: string;
            /** Lastframeassetid */
            lastFrameAssetId: string | null;
            /**
             * Provider
             * @constant
             */
            provider: "seedance";
            /** Model */
            model: string;
            /** Inputhash */
            inputHash: string;
            /** Durationms */
            durationMs: number;
            /** Bytesize */
            byteSize: number;
            /**
             * Mimetype
             * @constant
             */
            mimeType: "video/mp4";
            /** Width */
            width?: number | null;
            /** Height */
            height?: number | null;
            /** Adopted */
            adopted: boolean;
            /** Adoptionid */
            adoptionId: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
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
        /** WorkflowArtifactSnapshot */
        WorkflowArtifactSnapshot: {
            /** Artifactid */
            artifactId: string;
            /** Artifactrevision */
            artifactRevision: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "under_review" | "awaiting_user" | "applying" | "applied";
            /** Actionable */
            actionable: boolean;
            /** Reviewavailability */
            reviewAvailability?: ("complete" | "partial" | "unavailable") | null;
        };
        /** WorkflowClarificationSnapshot */
        WorkflowClarificationSnapshot: {
            /** Clarificationcode */
            clarificationCode: string;
            /** Prompt */
            prompt: string;
            /** Decisionstepid */
            decisionStepId: string;
        };
        /** WorkflowCurrentStepSnapshot */
        WorkflowCurrentStepSnapshot: {
            /** Stepid */
            stepId: string;
            /** Ordinal */
            ordinal: number;
            /** Purpose */
            purpose: string;
            /**
             * Lane
             * @enum {string}
             */
            lane: "control" | "interactive" | "creative" | "batch_media";
            modelProfile: components["schemas"]["ModelProfileRef"] | null;
            resolvedModel: components["schemas"]["ResolvedModelRef"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running" | "completed" | "failed" | "skipped";
            /** Attemptcount */
            attemptCount: number;
            /** Fencingtoken */
            fencingToken: number;
            latestProgress: components["schemas"]["WorkflowStepProgressSnapshot"] | null;
            /** Errorcode */
            errorCode?: string | null;
        };
        /** WorkflowErrorSnapshot */
        WorkflowErrorSnapshot: {
            /** Errorcode */
            errorCode: string;
            /** Failedstepid */
            failedStepId?: string | null;
            /** Outcomeunknown */
            outcomeUnknown: boolean;
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
        /** WorkflowStepProgressSnapshot */
        WorkflowStepProgressSnapshot: {
            /** Progresssequence */
            progressSequence: number;
            /**
             * Phase
             * @enum {string}
             */
            phase: "preparing" | "waiting_provider" | "validating" | "reporting";
            /** Elapsedseconds */
            elapsedSeconds: number;
            /** Waitingonprovider */
            waitingOnProvider: boolean;
            /**
             * Usagestatus
             * @enum {string}
             */
            usageStatus: "complete" | "partial" | "unknown";
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
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
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
            items: components["schemas"]["WritingRunPublicListItem"][];
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
        WritingRunPublicListItem: components["schemas"]["WritingRunListItem"] | components["schemas"]["WritingRunV2Response"];
        /** WritingRunResponse */
        WritingRunResponse: {
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string;
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
        WritingRunStartResponse: components["schemas"]["WritingRunResponse"] | components["schemas"]["WritingRunV2Response"];
        WritingRunStatusPublicResponse: components["schemas"]["WritingRunStatusResponse"] | components["schemas"]["WritingRunV2Response"];
        /** WritingRunStatusResponse */
        WritingRunStatusResponse: {
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 1;
            /** Runid */
            runId: string;
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
        /** WritingRunV2Response */
        WritingRunV2Response: {
            /** Workflow */
            workflow: string;
            /** Operation */
            operation?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "running" | "waiting_user" | "completed" | "failed" | "cancelled";
            /** Activesteps */
            activeSteps: components["schemas"]["WorkflowCurrentStepSnapshot"][];
            currentStep?: components["schemas"]["WorkflowCurrentStepSnapshot"] | null;
            /** Cancelrequestedat */
            cancelRequestedAt?: string | null;
            /** Lasteventsequence */
            lastEventSequence: number;
            /** Revision */
            revision: number;
            artifact?: components["schemas"]["WorkflowArtifactSnapshot"] | null;
            error?: components["schemas"]["WorkflowErrorSnapshot"] | null;
            clarification?: components["schemas"]["WorkflowClarificationSnapshot"] | null;
            /**
             * Engineversion
             * @constant
             */
            engineVersion: 2;
            /** Runid */
            runId: string;
            /** Taskid */
            taskId: string | null;
            /** Chapterid */
            chapterId: string | null;
            /**
             * Commandid
             * @enum {unknown}
             */
            commandId: null;
            /**
             * Commandstatus
             * @enum {unknown}
             */
            commandStatus: null;
            /** Reviewreport */
            reviewReport?: string | null;
            /** Candidateversionid */
            candidateVersionId?: string | null;
            /** Checkreport */
            checkReport?: {
                [key: string]: components["schemas"]["JsonValue"];
            } | null;
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
                    "text/event-stream": string;
                };
            };
            /** @description 统一错误响应 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description 统一错误响应 */
            default: {
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
