local project_dir = os.getenv("HOME") .. "/custom-ime"
local relay = project_dir .. "/scripts/ranker_relay"
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

local function send_request(request_json)
    local tmp = os.tmpname()
    local f = io.open(tmp, "w")
    if not f then
        return nil
    end
    f:write(request_json)
    f:close()

    local cmd = string.format("'%s' '%s' < '%s' 2>/dev/null", relay, socket_path, tmp)
    local sock = io.popen(cmd, "r")
    if not sock then
        os.remove(tmp)
        return nil
    end
    local response = sock:read("*a")
    sock:close()
    os.remove(tmp)
    if response and #response > 0 then
        return response
    end
    return nil
end

local function json_encode_candidates(candidates)
    local parts = {}
    for _, c in ipairs(candidates) do
        table.insert(parts, '"' .. json_escape(c) .. '"')
    end
    return "[" .. table.concat(parts, ",") .. "]"
end

local function json_decode_ranked(response_str)
    if not response_str then
        return nil
    end

    local array_part = response_str:match('"ranked"%s*:%s*(%b[])')
    if not array_part then
        return nil
    end

    local ranked = {}
    local i = 1
    local n = #array_part
    while i <= n do
        local ch = array_part:sub(i, i)
        if ch == '"' then
            i = i + 1
            local out = {}
            while i <= n do
                local c = array_part:sub(i, i)
                if c == '"' then
                    break
                end
                if c == "\\" then
                    local nxt = array_part:sub(i + 1, i + 1)
                    if nxt == '"' or nxt == "\\" or nxt == "/" then
                        table.insert(out, nxt)
                        i = i + 2
                    elseif nxt == "n" then
                        table.insert(out, "\n")
                        i = i + 2
                    elseif nxt == "r" then
                        table.insert(out, "\r")
                        i = i + 2
                    elseif nxt == "t" then
                        table.insert(out, "\t")
                        i = i + 2
                    elseif nxt == "u" then
                        local hex = array_part:sub(i + 2, i + 5)
                        if hex:match("^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
                            i = i + 6
                        else
                            i = i + 2
                        end
                    else
                        i = i + 2
                    end
                else
                    table.insert(out, c)
                    i = i + 1
                end
            end
            table.insert(ranked, table.concat(out))
        end
        i = i + 1
    end
    return ranked
end

local function rerank_filter(input, env)
    local candidates = {}
    local candidate_objs = {}

    for cand in input:iter() do
        table.insert(candidates, cand.text)
        candidate_objs[cand.text] = cand
    end

    if #candidates == 0 then
        return
    end

    local ctx = env.engine.context
    local context = ctx:get_commit_text() or ""
    local pinyin = ctx.input or ""
    local cand_json = json_encode_candidates(candidates)
    local request = string.format(
        '{"action":"rank","pinyin":"%s","context":"%s","candidates":%s}',
        json_escape(pinyin), json_escape(context), cand_json
    )

    local final_order = candidates
    local response = send_request(request)
    if response then
        local ranked = json_decode_ranked(response)
        if ranked and #ranked > 0 then
            final_order = ranked
            for _, word in ipairs(ranked) do
                local cand = candidate_objs[word]
                if cand then
                    yield(cand)
                    candidate_objs[word] = nil
                end
            end
        end
    end

    for _, word in ipairs(candidates) do
        if candidate_objs[word] then
            yield(candidate_objs[word])
        end
    end

    if ctx.set_property then
        ctx:set_property("custom_ime.last_pinyin", pinyin)
        ctx:set_property("custom_ime.last_context", context)
        ctx:set_property("custom_ime.last_candidates_json", json_encode_candidates(final_order))
        ctx:set_property("custom_ime.last_original_candidates_json", json_encode_candidates(candidates))
    end
end

return rerank_filter
