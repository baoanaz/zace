# langchain 基准题库（20 题）

> 靶场：`langchain` @ `41d3572`｜projectId `ca2050db0db5b1e2`｜索引：`/root/.zace/bench/voyage-4-lite-d1024`（复用，不重建）
> ⚠️ 出题时避开了**未进索引**的文件：`libs/core/langchain_core/runnables/base.py` 在索引时被跳过（体积/解析策略），
> 所以 Runnable/LCEL 相关题目只落在 `branch.py` / `fallbacks.py` / `retry.py` 等已索引文件上。
> 每题给出建议工具（`search` / `ask`）、人工核实的参考答案与依据路径；机器可跑版本见同目录 `langchain.jsonl`。

| ID | 建议工具 | 类别 | 问题 | 参考答案 | 依据 |
|---|---|---|---|---|---|
| LC-01 | `search` | symbol | 把 LLM 输出解析成 Pydantic 模型的解析器类定义在哪个文件？ | libs/core/langchain_core/output_parsers/pydantic.py 的 PydanticOutputParser（继承 JsonOutputParser，用模型的 JSON schema 生成格式说明并校验）。 | `libs/core/langchain_core/output_parsers/pydantic.py#PydanticOutputParser` |
| LC-02 | `search` | symbol | RecursiveCharacterTextSplitter 默认按什么顺序尝试分隔符？ | 默认 separators = ["\n\n", "\n", " ", ""]，keep_separator=True，可选 is_separator_regex 把分隔符当正则；递归逐级尝试直到片段够小。 | `libs/text-splitters/langchain_text_splitters/character.py#RecursiveCharacterTextSplitter` |
| LC-03 | `search` | symbol | 按 token 预算裁剪消息列表的函数在哪个文件？ | libs/core/langchain_core/messages/utils.py 的 trim_messages。 | `libs/core/langchain_core/messages/utils.py#trim_messages` |
| LC-04 | `search` | symbol | ChatPromptTemplate 的 from_messages 类方法在哪个文件？ | libs/core/langchain_core/prompts/chat.py 的 ChatPromptTemplate.from_messages。 | `libs/core/langchain_core/prompts/chat.py#ChatPromptTemplate` |
| LC-05 | `search` | symbol | 所有工具类的基类 BaseTool 定义在哪，它是什么类型的 Runnable？ | libs/core/langchain_core/tools/base.py 的 BaseTool，是 RunnableSerializable[str | dict | ToolCall, Any]（另见 BaseToolkit）。 | `libs/core/langchain_core/tools/base.py#BaseTool` |
| LC-06 | `search` | path | 把普通函数装饰成工具的 @tool 实现在哪个文件？ | libs/core/langchain_core/tools/convert.py（多个重载的 tool(...)，负责推断参数 schema 与 docstring 描述）。 | `libs/core/langchain_core/tools/convert.py#tool` |
| LC-07 | `ask` | behavior | 自己实现一个向量库（VectorStore 子类）时，最少必须实现哪些方法？add_documents 还需要自己写吗？ | 必须实现 add_texts 与 similarity_search（抽象方法）；add_documents 不必自己写——基类默认基于 add_texts 实现（并保持返回 ids 与 documents 对应）。可选覆盖 similarity_search_with_score 等以获得更细能力。 | `libs/core/langchain_core/vectorstores/base.py#VectorStore` |
| LC-08 | `search` | path | langchain_core 自带的进程内向量库实现是哪个文件、哪个类？ | libs/core/langchain_core/vectorstores/in_memory.py 的 InMemoryVectorStore。 | `libs/core/langchain_core/vectorstores/in_memory.py#InMemoryVectorStore` |
| LC-09 | `search` | symbol | LLM 响应缓存的抽象基类与默认内存实现在哪个文件？ | libs/core/langchain_core/caches.py：BaseCache（抽象）与 InMemoryCache（默认内存实现）。 | `libs/core/langchain_core/caches.py#BaseCache` |
| LC-10 | `ask` | behavior | BaseRetriever 和 VectorStoreRetriever 是什么关系？向量库怎么变成一个检索器？ | VectorStoreRetriever 是 BaseRetriever 的子类，内部持有 vectorstore 与 search_kwargs；向量库通过 VectorStore.as_retriever(**kwargs) 生成它。BaseRetriever 要求实现 _get_relevant_documents（新版为 aget 风格接口）。 | `libs/core/langchain_core/retrievers.py#BaseRetriever`<br>`libs/core/langchain_core/vectorstores/base.py#VectorStoreRetriever` |
| LC-11 | `search` | symbol | embedding 模型的抽象基类叫什么、在哪个文件？ | Embeddings（ABC），定义在 libs/core/langchain_core/embeddings/embeddings.py，要求实现 embed_documents / embed_query。 | `libs/core/langchain_core/embeddings/embeddings.py#Embeddings` |
| LC-12 | `search` | symbol | Document 类定义在哪，它继承自什么？ | libs/core/langchain_core/documents/base.py 的 Document(BaseMedia)（pdf/图片等内容可通过 BaseMedia 承载）。 | `libs/core/langchain_core/documents/base.py#Document` |
| LC-13 | `search` | symbol | 聊天模型的基类 BaseChatModel 在哪个文件，它的基类是什么？ | libs/core/langchain_core/language_models/chat_models.py 的 BaseChatModel(BaseLanguageModel[AIMessage], ABC)。 | `libs/core/langchain_core/language_models/chat_models.py#BaseChatModel` |
| LC-14 | `ask` | behavior | langchain_core.indexing 的 index() 是怎么判断「该跳过 / 该更新 / 该删除」的？cleanup 有哪几种模式？ | 靠 record_manager（RecordManager）记录每个文档的 key 与写入时间：内容 hash（key_encoder 默认 sha1）+ 时间戳决定 skip/update；cleanup 支持 incremental / full / scoped_full 三种清理模式，另有 batch_size、cleanup_batch_size、force_update 等参数。 | `libs/core/langchain_core/indexing/api.py#index` |
| LC-15 | `search` | symbol | 追踪器基类 BaseTracer 定义在哪，它继承什么？ | libs/core/langchain_core/tracers/base.py 的 BaseTracer(_TracerCore, BaseCallbackHandler, ABC)。 | `libs/core/langchain_core/tracers/base.py#BaseTracer` |
| LC-16 | `ask` | behavior | RunnableWithFallbacks、RunnableRetry、RunnableBranch 各自解决什么问题？ | fallbacks.py：主 Runnable 失败时按顺序尝试备用（常用于换 provider）；retry.py：对失败的 Runnable 做重试（可配置异常类型/策略）；branch.py：按条件把输入路由到不同分支（RunnableBranch）。 | `libs/core/langchain_core/runnables/fallbacks.py#RunnableWithFallbacks`<br>`libs/core/langchain_core/runnables/retry.py#RunnableRetry`<br>`libs/core/langchain_core/runnables/branch.py#RunnableBranch` |
| LC-17 | `search` | behavior | TextSplitter 的 split_text 和 create_documents 是什么关系？ | split_text 是抽象方法（子类实现真正的切分），create_documents 是基类默认实现：先对每段文本调用 split_text，再把结果包成 Document（可带 metadatas）。 | `libs/text-splitters/langchain_text_splitters/base.py#TextSplitter` |
| LC-18 | `ask` | behavior | ChatPromptTemplate.from_messages 支持哪几种写法来做占位？ | 支持：纯字符串（当 system/human 文本）、("role", "text") 元组、BaseMessage 实例或类（会转成消息提示模板）、以及 MessagesPlaceholder 用于注入整段消息历史；模板字符串里用 {} 变量占位。 | `libs/core/langchain_core/prompts/chat.py#ChatPromptTemplate`<br>`libs/core/langchain_core/prompts/chat.py#MessagesPlaceholder` |
| LC-19 | `search` | path | 基于 rank_bm25 的检索器实现放在哪个文件？ | libs/langchain/langchain_classic/retrievers/bm25.py（同目录另有 elastic_search_bm25.py）。 | `libs/langchain/langchain_classic/retrievers/bm25.py` |
| LC-20 | `search` | negative | langchain_core 内置的 SQLite FTS5 全文检索实现在哪个文件？ | 不存在：langchain_core 没有 SQLite/FTS5 全文检索实现（核心只提供向量库抽象与 BM25 等第三方后端集成）。 | （无：负例） |

## 统计

- 共 20 题：`search` 14 题、`ask` 5 题、负例 1 题。
