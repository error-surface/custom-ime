local json_helper = require("json_helper")

local socket_path = os.getenv("HOME") .. "/.local/share/custom-ime/ranker.sock"
local script_dir = debug.getinfo(1, "S").source:match("^@(.+)/[^/]+$") or "."
local client_script = script_dir .. "/../../scripts/ranker_client.py"

local function send_request(request_json)
    local cmd = string.format(
        "python3 '%s' '%s' '%s' 2>/dev/null",
        client_script:gsub("'", "'\\''"),
        socket_path:gsub("'", "'\\''"),
        request_json:gsub("'", "'\\''")
    )
    local sock = io.popen(cmd, "r")
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
    local context2 = ctx:get_property and (ctx:get_property("custom_ime.prev_word2") or "") or ""
    local cand_json = json_helper.encode(candidates)
    local request = json_helper.encode({
        action = "rank",
        pinyin = pinyin,
        context = context,
        context2 = context2,
        candidates = candidates,
    })

    -- Default: preserve original order if the ranker is unavailable.
    local final_order = candidates

    local response = send_request(request)
    if response then
        local decoded, err = json_helper.decode(response)
        if decoded and decoded.ranked and #decoded.ranked > 0 then
            final_order = decoded.ranked
            for _, word in ipairs(decoded.ranked) do
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
        ctx:set_property("custom_ime.last_candidates_json", json_helper.encode(final_order))
    end
end

return rerank_filter
