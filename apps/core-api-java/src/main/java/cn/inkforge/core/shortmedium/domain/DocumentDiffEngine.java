package cn.inkforge.core.shortmedium.domain;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import tools.jackson.databind.ObjectMapper;

/**
 * 与 Python {@code difflib.SequenceMatcher(autojunk=False)} 对齐的段落差异引擎。
 *
 * <p>不能换成 UTF-16 字符差异：公开确认哈希和选区位置都以 Unicode code point 为准。
 */
public final class DocumentDiffEngine {

    private static final Pattern PARAGRAPH_SEPARATOR = Pattern.compile("\\n[ \\t]*\\n");
    private static final ObjectMapper JSON = new ObjectMapper();

    private DocumentDiffEngine() {}

    public static DocumentDiff build(
            String before,
            String after,
            String fromVersionId,
            String toVersionId) {
        List<String> oldParts = paragraphs(before);
        List<String> newParts = paragraphs(after);
        int[] oldOffsets = offsets(oldParts);
        int[] newOffsets = offsets(newParts);
        List<DocumentDiffBlock> blocks = new ArrayList<>();
        for (Opcode opcode : opcodes(oldParts, newParts)) {
            if ("equal".equals(opcode.type())) {
                continue;
            }
            String oldText = join(oldParts, opcode.oldStart(), opcode.oldEnd());
            String newText = join(newParts, opcode.newStart(), opcode.newEnd());
            blocks.add(new DocumentDiffBlock(
                    opcode.type(),
                    oldOffsets[opcode.oldStart()],
                    oldOffsets[opcode.oldEnd()],
                    newOffsets[opcode.newStart()],
                    newOffsets[opcode.newEnd()],
                    "insert".equals(opcode.type()) ? null : oldText,
                    "delete".equals(opcode.type()) ? null : newText));
        }
        int fromWordCount = ShortMediumText.count(before);
        int toWordCount = ShortMediumText.count(after);
        DocumentDiff draft = new DocumentDiff(
                fromVersionId,
                toVersionId,
                fromWordCount,
                toWordCount,
                toWordCount - fromWordCount,
                blocks,
                "0".repeat(64));
        return bind(
                draft,
                null,
                null,
                fromVersionId,
                ShortMediumText.sha256(before),
                toVersionId);
    }

    public static DocumentDiff bind(
            DocumentDiff diff,
            String documentType,
            String chapterId,
            String baseVersionId,
            String currentDraftHash,
            String targetVersionId) {
        TreeMap<String, Object> canonical = new TreeMap<>();
        canonical.put("documentType", documentType);
        canonical.put("chapterId", chapterId);
        canonical.put("baseVersionId", baseVersionId);
        canonical.put("currentDraftHash", currentDraftHash);
        canonical.put("targetVersionId", targetVersionId);
        canonical.put("diff", canonicalDiff(diff));
        String hash = ShortMediumText.sha256(JSON.writeValueAsString(canonical));
        return diff.withConfirmationHash(hash);
    }

    private static Map<String, Object> canonicalDiff(DocumentDiff diff) {
        TreeMap<String, Object> result = new TreeMap<>();
        result.put("fromVersionId", diff.fromVersionId());
        result.put("toVersionId", diff.toVersionId());
        result.put("fromWordCount", diff.fromWordCount());
        result.put("toWordCount", diff.toWordCount());
        result.put("wordCountDelta", diff.wordCountDelta());
        result.put("blocks", diff.blocks().stream().map(block -> {
            TreeMap<String, Object> value = new TreeMap<>();
            value.put("type", block.type());
            value.put("oldStart", block.oldStart());
            value.put("oldEnd", block.oldEnd());
            value.put("newStart", block.newStart());
            value.put("newEnd", block.newEnd());
            value.put("oldText", block.oldText());
            value.put("newText", block.newText());
            return value;
        }).toList());
        return result;
    }

    private static List<String> paragraphs(String content) {
        if (content.isEmpty()) {
            return List.of();
        }
        List<String> result = new ArrayList<>();
        Matcher matcher = PARAGRAPH_SEPARATOR.matcher(content);
        int start = 0;
        while (matcher.find()) {
            result.add(content.substring(start, matcher.end()));
            start = matcher.end();
        }
        if (start < content.length()) {
            result.add(content.substring(start));
        }
        return result;
    }

    private static int[] offsets(List<String> parts) {
        int[] offsets = new int[parts.size() + 1];
        for (int index = 0; index < parts.size(); index++) {
            offsets[index + 1] = offsets[index] + ShortMediumText.codePointLength(parts.get(index));
        }
        return offsets;
    }

    private static String join(List<String> parts, int start, int end) {
        StringBuilder result = new StringBuilder();
        for (int index = start; index < end; index++) {
            result.append(parts.get(index));
        }
        return result.toString();
    }

    private static List<Opcode> opcodes(List<String> first, List<String> second) {
        List<Opcode> result = new ArrayList<>();
        int oldIndex = 0;
        int newIndex = 0;
        for (Match match : matchingBlocks(first, second)) {
            String type = null;
            if (oldIndex < match.oldStart() && newIndex < match.newStart()) {
                type = "replace";
            } else if (oldIndex < match.oldStart()) {
                type = "delete";
            } else if (newIndex < match.newStart()) {
                type = "insert";
            }
            if (type != null) {
                result.add(new Opcode(
                        type,
                        oldIndex,
                        match.oldStart(),
                        newIndex,
                        match.newStart()));
            }
            if (match.size() > 0) {
                result.add(new Opcode(
                        "equal",
                        match.oldStart(),
                        match.oldStart() + match.size(),
                        match.newStart(),
                        match.newStart() + match.size()));
            }
            oldIndex = match.oldStart() + match.size();
            newIndex = match.newStart() + match.size();
        }
        return result;
    }

    private static List<Match> matchingBlocks(List<String> first, List<String> second) {
        Map<String, List<Integer>> secondIndexes = new HashMap<>();
        for (int index = 0; index < second.size(); index++) {
            secondIndexes.computeIfAbsent(second.get(index), ignored -> new ArrayList<>())
                    .add(index);
        }
        List<Match> matches = new ArrayList<>();
        Deque<Range> queue = new ArrayDeque<>();
        queue.push(new Range(0, first.size(), 0, second.size()));
        while (!queue.isEmpty()) {
            Range range = queue.pop();
            Match match = longestMatch(first, secondIndexes, range);
            if (match.size() == 0) {
                continue;
            }
            matches.add(match);
            if (range.oldStart() < match.oldStart()
                    && range.newStart() < match.newStart()) {
                queue.push(new Range(
                        range.oldStart(),
                        match.oldStart(),
                        range.newStart(),
                        match.newStart()));
            }
            if (match.oldStart() + match.size() < range.oldEnd()
                    && match.newStart() + match.size() < range.newEnd()) {
                queue.push(new Range(
                        match.oldStart() + match.size(),
                        range.oldEnd(),
                        match.newStart() + match.size(),
                        range.newEnd()));
            }
        }
        matches.sort(Comparator.comparingInt(Match::oldStart).thenComparingInt(Match::newStart));
        List<Match> collapsed = new ArrayList<>();
        for (Match match : matches) {
            if (!collapsed.isEmpty()) {
                Match previous = collapsed.getLast();
                if (previous.oldStart() + previous.size() == match.oldStart()
                        && previous.newStart() + previous.size() == match.newStart()) {
                    collapsed.set(
                            collapsed.size() - 1,
                            new Match(previous.oldStart(), previous.newStart(), previous.size() + match.size()));
                    continue;
                }
            }
            collapsed.add(match);
        }
        collapsed.add(new Match(first.size(), second.size(), 0));
        return collapsed;
    }

    private static Match longestMatch(
            List<String> first,
            Map<String, List<Integer>> secondIndexes,
            Range range) {
        int bestOld = range.oldStart();
        int bestNew = range.newStart();
        int bestSize = 0;
        Map<Integer, Integer> previousLengths = Map.of();
        for (int oldIndex = range.oldStart(); oldIndex < range.oldEnd(); oldIndex++) {
            Map<Integer, Integer> currentLengths = new HashMap<>();
            for (int newIndex : secondIndexes.getOrDefault(first.get(oldIndex), List.of())) {
                if (newIndex < range.newStart()) {
                    continue;
                }
                if (newIndex >= range.newEnd()) {
                    break;
                }
                int size = previousLengths.getOrDefault(newIndex - 1, 0) + 1;
                currentLengths.put(newIndex, size);
                if (size > bestSize) {
                    bestOld = oldIndex - size + 1;
                    bestNew = newIndex - size + 1;
                    bestSize = size;
                }
            }
            previousLengths = currentLengths;
        }
        return new Match(bestOld, bestNew, bestSize);
    }

    private record Range(int oldStart, int oldEnd, int newStart, int newEnd) {}

    private record Match(int oldStart, int newStart, int size) {}

    private record Opcode(String type, int oldStart, int oldEnd, int newStart, int newEnd) {}
}
