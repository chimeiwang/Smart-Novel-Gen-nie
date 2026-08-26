package cn.inkforge.core.lore.domain;

/** 长篇设定库中可以独立增删改查的五类实体。 */
public enum LoreEntityKind {
    CHARACTERS("characters"),
    ITEMS("items"),
    LOCATIONS("locations"),
    FACTIONS("factions"),
    GLOSSARY("glossary");

    private final String value;

    LoreEntityKind(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
