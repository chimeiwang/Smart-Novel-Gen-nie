export type AsyncAction<T> = () => Promise<T>;

export type AsyncActionGuard = {
  readonly isRunning: () => boolean;
  run: <T>(action: AsyncAction<T>) => Promise<T> | undefined;
};

export function createAsyncActionGuard(): AsyncActionGuard {
  let running = false;

  return {
    isRunning: () => running,
    run: <T>(action: AsyncAction<T>) => {
      if (running) return undefined;
      running = true;
      try {
        return Promise.resolve(action()).finally(() => {
          running = false;
        });
      } catch (error) {
        running = false;
        return Promise.reject(error);
      }
    },
  };
}
