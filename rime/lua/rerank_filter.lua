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
    -- Escape other ASCII control chars.
    s = s:gsub("[%z\1-\31]", function(c)
        return string.format("\\u%04x", c:byte())
    end)
    return s
end

local function send_request(request_json)
    local sock = io.popen(
        string.format(
            "echo '%s' | nc -U '%s' -w 1 2>/dev/null",
            request_json:gsub("'", "'\\''"),
            socket_path
        ),
        "r"
    )
    if not sock then
        return nil
    end
    local response = sock:read("*a")
    sock:close()
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

    -- Extract the JSON array under the "ranked" key.
    local array_part = response_str:match('"ranked"%s*:%s*(%b[])')
    if not array_part then
        return nil
    end

    local ranked = {}

    -- Parse a JSON array of strings with minimal escape support.
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
                            -- Keep unicode escapes as-is; candidates are expected to be UTF-8 already.
                            -- This is mostly to avoid breaking the parser.
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

    -- Default: preserve original order if the ranker is unavailable.
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

    -- Persist last candidate order for selection logging.
    if ctx.set_property then
        ctx:set_property("custom_ime.last_pinyin", pinyin)
        ctx:set_property("custom_ime.last_context", context)
        ctx:set_property("custom_ime.last_candidates_json", json_encode_candidates(final_order))
    end
end

return rerank_filter
