local socket_path = os.getenv("HOME") .. "/.local/share/custom-ime/ranker.sock"

local function json_escape(s)
    if s == nil then
        return ""
    end
    s = tostring(s)
    s = s:gsub("\\", "\\\\")
    s = s:gsub('"', '\\"')
    s = s:gsub("\r", "\\r")
    s = s:gsub("\n", "\\n")
    s = s:gsub("\t", "\\t")
    s = s:gsub("[%z\1-\31]", function(c)
        return string.format("\\u%04x", c:byte())
    end)
    return s
end

local function json_decode_string_array(s)
    if not s then
        return nil
    end
    -- Expect a JSON array like ["a","b"].
    if not s:match("^%s*%[") then
        return nil
    end
    local out = {}
    local i = 1
    local n = #s
    while i <= n do
        local ch = s:sub(i, i)
        if ch == '"' then
            i = i + 1
            local buf = {}
            while i <= n do
                local c = s:sub(i, i)
                if c == '"' then
                    break
                end
                if c == "\\" then
                    local nxt = s:sub(i + 1, i + 1)
                    if nxt == '"' or nxt == "\\" or nxt == "/" then
                        table.insert(buf, nxt)
                        i = i + 2
                    elseif nxt == "n" then
                        table.insert(buf, "\n")
                        i = i + 2
                    elseif nxt == "r" then
                        table.insert(buf, "\r")
                        i = i + 2
                    elseif nxt == "t" then
                        table.insert(buf, "\t")
                        i = i + 2
                    elseif nxt == "u" then
                        local hex = s:sub(i + 2, i + 5)
                        if hex:match("^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
                            i = i + 6
                        else
                            i = i + 2
                        end
                    else
                        i = i + 2
                    end
                else
                    table.insert(buf, c)
                    i = i + 1
                end
            end
            table.insert(out, table.concat(buf))
        end
        i = i + 1
    end
    return out
end

local function send_fire_and_forget(request_json)
    os.execute(string.format(
        "echo '%s' | nc -U '%s' -w 1 &>/dev/null &",
        request_json:gsub("'", "'\\''"),
        socket_path
    ))
end

local function select_notifier(env)
    env.notifier = env.engine.context.select_notifier:connect(function(ctx)
        local text = ctx:get_commit_text()
        if not text or #text == 0 then
            return
        end

        local pinyin = ctx:get_property and (ctx:get_property("custom_ime.last_pinyin") or ctx.input) or (ctx.input or "")
        local context = ctx:get_property and (ctx:get_property("custom_ime.last_context") or "") or ""
        local candidates_json = ctx:get_property and (ctx:get_property("custom_ime.last_candidates_json") or "[]") or "[]"
        local candidates = json_decode_string_array(candidates_json) or {}

        local pos = 0
        for i, w in ipairs(candidates) do
            if w == text then
                pos = i - 1
                break
            end
        end

        local request = string.format(
            '{"action":"select","pinyin":"%s","context":"%s","chosen":"%s","candidates":%s,"position":%d}',
            json_escape(pinyin), json_escape(context), json_escape(text), candidates_json, pos
        )
        send_fire_and_forget(request)
    end)
end

local function fini(env)
    if env.notifier then
        env.notifier:disconnect()
    end
end

return { init = select_notifier, func = function() end, fini = fini }
