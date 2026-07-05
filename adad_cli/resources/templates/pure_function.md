# Pure Function 模式規範

## 說明
此節點必須實作為無副作用的純函數 (Pure Function)。

## 程式碼規範
- 輸入引數必須為 immutable，禁止在函數內修改傳入的參數。
- 函數返回值僅由輸入引數決定，禁止存取 any 外部全域變量。
- 禁止呼叫 any side effect 函數 (I/O, DB, Network)...
