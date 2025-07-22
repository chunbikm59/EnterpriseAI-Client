import re
from fastmcp import FastMCP, Context

mcp = FastMCP(name="user_custom_prompt", json_response=False, stateless_http=False)


def register_mcp_tool(func_name: str, describe: str, return_string, namespace=None):
    # 預設註冊到目前全域空間
    if namespace is None:
        namespace = globals()

    # 驗證函數名稱（支援中英文）
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', func_name):
        raise ValueError("函數名稱不合法，請使用英文、數字、底線組合，且不得以數字開頭")

    # 處理字串內容，避免注入（repr 會自動加上引號和跳脫）
    safe_return = repr(return_string)

    # 組成代碼
    func_code = f'''
@mcp.tool()
def {func_name}():
    """{describe}"""
    return {safe_return}
'''

    # 執行代碼並註冊到 namespace（預設為全域）
    exec(func_code, namespace)

    return namespace[func_name]


if __name__ == "__main__":
    # 可以從資料庫取得使用者設定的prompt動態產生mcp tool
    # 這可以讓模型可以根據問題自動載入相關的prompt。這讓使用者可以用簡短的命令來觸發複雜的流程
    # 以下範例可以讓使用者輸入: "幫我請假" 觸發模型自主查看prompt來了解完整請假流程。
    register_mcp_tool(
        func_name="prompt_1", 
        describe="請假流程",  # 這會影響模型是否能根據情境選擇正確的prompt來閱讀
        return_string='''
            1. 先到myHR系統(http:myhr)點擊請假，未指定就預設選擇特休假，未指定日期預設為當天8點到17點。
            2. 保存假單->送簽
            3. 如果有截圖工具就到"已送出假單"的頁面中螢幕截圖給我確認
            4. 到部門的公用行事曆幫我標記請假，完成後螢幕截圖給我確認
        ''')
    mcp.run()