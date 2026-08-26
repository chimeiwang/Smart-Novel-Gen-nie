package cn.inkforge.cli.runtime;

import cn.inkforge.cli.config.ConfigStore;
import cn.inkforge.cli.config.CredentialStore;
import cn.inkforge.cli.transport.CoreApi;
import java.util.function.BooleanSupplier;
import tools.jackson.databind.ObjectMapper;

public record CliDependencies(
        ApiFactory apiFactory,
        ConfigStore configStore,
        CredentialStore credentialStore,
        PasswordReader passwordReader,
        BooleanSupplier stdinIsTty,
        ObjectMapper json,
        MonotonicClock monotonicClock,
        Sleeper sleeper) {

    public CliDependencies(
            ApiFactory apiFactory,
            ConfigStore configStore,
            CredentialStore credentialStore,
            PasswordReader passwordReader,
            BooleanSupplier stdinIsTty,
            ObjectMapper json) {
        this(
                apiFactory,
                configStore,
                credentialStore,
                passwordReader,
                stdinIsTty,
                json,
                () -> System.nanoTime() / 1_000_000_000.0,
                seconds -> {
                    long millis = Math.max(0L, Math.round(seconds * 1000.0));
                    Thread.sleep(millis);
                });
    }

    @FunctionalInterface
    public interface ApiFactory {
        CoreApi create(String origin, String token);
    }

    @FunctionalInterface
    public interface PasswordReader {
        char[] read(String prompt);
    }

    @FunctionalInterface
    public interface MonotonicClock {
        double now();
    }

    @FunctionalInterface
    public interface Sleeper {
        void sleep(double seconds) throws InterruptedException;
    }
}
