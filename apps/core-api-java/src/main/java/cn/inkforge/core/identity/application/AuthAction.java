package cn.inkforge.core.identity.application;

public enum AuthAction {
    LOGIN("login"),
    REGISTER("register");

    private final String key;

    AuthAction(String key) {
        this.key = key;
    }

    public String key() {
        return key;
    }
}
