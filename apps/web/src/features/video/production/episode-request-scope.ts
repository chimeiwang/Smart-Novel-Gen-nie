/** 切集和重载各自推进代次；迟到的请求只更新其命令回执，不更新当前工作面。 */
export class EpisodeRequestScope {
  #generation = 0;
  next(): () => boolean {
    const generation = ++this.#generation;
    return () => this.#generation === generation;
  }
  dispose(): void { this.#generation += 1; }
}

/** 异步写入闭包使用会话上下文，React 状态仍通过回读单独更新。 */
export class EpisodeSessionContext<T> {
  #detail: T;
  #alive = true;
  constructor(detail: T) { this.#detail = detail; }
  get detail(): T { return this.#detail; }
  get alive(): boolean { return this.#alive; }
  update(detail: T): void { this.#detail = detail; }
  activate(): void { this.#alive = true; }
  dispose(): void { this.#alive = false; }
}
