local socket_path = os.getenv("HOME") .. "/.local/share/custom-ime/ranker.sock"

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
        table.insert(parts, '"' .. c .. '"')
    end
    return "[" .. table.concat(parts, ",") .. "]"
end

local function json_decode_ranked(response_str)
    local ranked = {}
    for word in response_str:gmatch('"([^"]+)"') do
        table.insert(ranked, word)
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

    local context = env.engine.context:get_commit_text() or ""
    local pinyin = env.engine.context.input or ""
    local cand_json = json_encode_candidates(candidates)
    local request = string.format(
        '{"action":"rank","pinyin":"%s","context":"%s","candidates":%s}',
        pinyin, context, cand_json
    )

    local response = send_request(request)
    if response then
        local ranked = json_decode_ranked(response)
        for _, word in ipairs(ranked) do
            local cand = candidate_objs[word]
            if cand then
                yield(cand)
                candidate_objs[word] = nil
            end
        end
    end

    for _, word in ipairs(candidates) do
        if candidate_objs[word] then
            yield(candidate_objs[word])
        end
    end
end

return rerank_filter
