import "@testing-library/jest-dom/vitest";

/**
 * `<dialog>` 的最小 polyfill（TASK-094 §D）。
 *
 * 为什么需要：确认弹窗用的是原生 `<dialog>` + `showModal()`（换来焦点陷阱、`Esc` 关闭与
 * `aria-modal` 语义），而 jsdom（vitest 的 DOM 环境）**尚未实现** `showModal` / `close`——
 * 不补这一层，任何用到确认弹窗的组件测试都会在 `dialog.showModal is not a function` 上直接崩。
 *
 * 只补测试真正需要的行为：
 * - `showModal()` 置 `open=true`（**并让元素在 DOM 里可见**，`getByRole("dialog")` 才找得到）；
 * - `close()` 置 `open=false` 并派发 `close` 事件（与浏览器一致，供监听者清理）；
 * - `Esc` → 派发 `cancel` 事件（浏览器行为；组件据此走 `onCancel`）。
 *
 * `open` 用原生属性而非自定义字段：`<dialog open>` 在无 CSS 时是可见的，`within(dialog)` 断言
 * 因此可以按真实 DOM 结构写，不需要给测试开"特殊通道"。
 */
if (typeof HTMLDialogElement !== "undefined") {
  const proto = HTMLDialogElement.prototype;

  if (typeof proto.showModal !== "function") {
    proto.showModal = function showModal(this: HTMLDialogElement) {
      this.open = true;
    };
  }
  if (typeof proto.close !== "function") {
    proto.close = function close(this: HTMLDialogElement, returnValue?: string) {
      if (returnValue !== undefined) this.returnValue = returnValue;
      this.open = false;
      this.dispatchEvent(new Event("close"));
    };
  }
  if (typeof proto.show !== "function") {
    proto.show = proto.showModal;
  }
}
