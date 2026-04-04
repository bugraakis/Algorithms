import java.util.Random;
import java.util.Scanner;
import java.io.*;

/**
 * Tile Matching Game
 *
 * Rules:
 *  - 5 tile sets (Stacks), each holding 1–10 unique letters, max capacity 10.
 *  - Reserve Queue: 26 shuffled letters; used by AddSet command.
 *  - Supplementary Queue: 26 shuffled letters; auto-adds every 3 valid steps.
 *  - Commands: Match(i,j), AddSet(i), ShiftQueue, F (finish).
 *  - Matching equal top tiles earns +5 points.
 *  - AddSet when shift rights are exhausted costs -2 points.
 *  - High Score Table (top 10) is persisted in "HighScoreTable.txt".
 */
public class TileMatchingGame {

    // ----- Game data structures -----
    @SuppressWarnings("unchecked")
    static Stack<Character>[] sets = new Stack[5];           // 5 tile sets
    static Queue<Character>   reserveQueue       = new Queue<>(30); // 26 letters max
    static Queue<Character>   supplementaryQueue = new Queue<>(30); // 26 letters max
    static Queue<PlayerScore> highScoreTable     = new Queue<>(11); // top 10 entries

    // ----- Game state -----
    static int    score;
    static int    stepCount;
    static int    maxSteps;
    static int    shiftRights;
    static String playerName;

    // Last command result / auto-add message shown in the status panel
    static String lastMessage = "";

    // ----- Constants -----
    static final int    SET_COUNT       = 5;
    static final int    SET_CAPACITY    = 10;
    static final int    HIGH_SCORE_MAX  = 10;
    static final String HIGH_SCORE_FILE = "HighScoreTable.txt";

    // ANSI colour codes
    static final String RESET  = "\u001B[0m";
    static final String BOLD   = "\u001B[1m";
    static final String GREEN  = "\u001B[32m";
    static final String YELLOW = "\u001B[33m";
    static final String CYAN   = "\u001B[36m";
    static final String RED    = "\u001B[31m";
    static final String WHITE  = "\u001B[37m";

    // ============================================================
    //  MAIN
    // ============================================================
    public static void main(String[] args) throws IOException {

        Scanner scanner = new Scanner(System.in);
        Random  random  = new Random();

        clearScreen();

        // --- Player name ---
        System.out.print(BOLD + "Enter player name: " + RESET);
        playerName = scanner.nextLine().trim();

        // --- Initialise sets ---
        for (int i = 0; i < SET_COUNT; i++) {
            sets[i] = new Stack<>(SET_CAPACITY);
        }

        int totalInitialTiles = 0;
        for (int i = 0; i < SET_COUNT; i++) {
            // Each set gets its own shuffled alphabet → letters unique within set,
            // may repeat across sets (needed so matching is actually possible).
            char[] pool  = shuffleAlphabet(random);
            int    count = random.nextInt(SET_CAPACITY) + 1; // 1 .. 10
            for (int j = 0; j < count; j++) {
                sets[i].push(pool[j]);
                totalInitialTiles++;
            }
        }

        // --- Game parameters ---
        maxSteps    = (int)(totalInitialTiles * 1.2);
        shiftRights = random.nextInt(5) + 1;   // 1 .. 5
        score       = 0;
        stepCount   = 0;
        lastMessage = CYAN + "Game started! Good luck, " + playerName + "!" + RESET;

        // --- Initialise reserve queue (26 shuffled letters) ---
        char[] rPool = shuffleAlphabet(random);
        for (char c : rPool) reserveQueue.enqueue(c);

        // --- Initialise supplementary queue (26 shuffled letters) ---
        char[] sPool = shuffleAlphabet(random);
        for (char c : sPool) supplementaryQueue.enqueue(c);

        // --- Load high scores ---
        loadHighScores();

        // Initial screen render
        displayGameState();

        // ============================================================
        //  GAME LOOP
        // ============================================================
        gameLoop:
        while (true) {

            // Check end conditions at the START of each turn
            if (allSetsEmpty()) {
                lastMessage = RED + "*** All sets are empty! Game over! ***" + RESET;
                displayGameState();
                break;
            }
            if (stepCount >= maxSteps) {
                lastMessage = RED + "*** Maximum step limit (" + maxSteps + ") reached! Game over! ***" + RESET;
                displayGameState();
                break;
            }

            System.out.print(BOLD + ">> " + RESET);
            String cmd = scanner.nextLine().trim();

            boolean validStep = false;

            if (cmd.equalsIgnoreCase("F")) {
                lastMessage = YELLOW + "Player ended the game." + RESET;
                break gameLoop;

            } else if (cmd.startsWith("Match(") && cmd.endsWith(")")) {
                validStep = doMatch(cmd);

            } else if (cmd.startsWith("AddSet(") && cmd.endsWith(")")) {
                validStep = doAddSet(cmd);

            } else if (cmd.equals("ShiftQueue")) {
                validStep = doShiftQueue();

            } else {
                lastMessage = RED + "Unknown command! Valid: Match(i,j)  AddSet(i)  ShiftQueue  F" + RESET;
            }

            if (validStep) {
                stepCount++;

                // Every 3 valid steps → auto-add from supplementary queue
                if (stepCount % 3 == 0) {
                    doAutoAdd();
                }

                displayGameState();

                // Check end conditions AFTER the step (for immediate termination)
                if (allSetsEmpty()) {
                    lastMessage = RED + "*** All sets are empty! Game over! ***" + RESET;
                    displayGameState();
                    break;
                }
                if (stepCount >= maxSteps) {
                    lastMessage = RED + "*** Maximum step limit (" + maxSteps + ") reached! Game over! ***" + RESET;
                    displayGameState();
                    break;
                }
            } else {
                // Re-render so the error message is visible in the status panel
                displayGameState();
            }
        }

        // ============================================================
        //  GAME OVER
        // ============================================================
        clearScreen();
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.println(BOLD + "               GAME OVER"                  + RESET);
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.println("Player     : " + BOLD + playerName + RESET);
        System.out.println("Final Score: " + BOLD + GREEN + score + RESET);
        System.out.println("Steps taken: " + stepCount + " / " + maxSteps);
        System.out.println(BOLD + "==========================================" + RESET);

        updateHighScores(playerName, score);
        displayHighScores();
        saveHighScores();

        scanner.close();
    }

    // ============================================================
    //  COMMAND HANDLERS
    // ============================================================

    /**
     * Handles Match(i,j): compares the top tiles of Set-i and Set-j.
     * Equal → removes both, +5 pts.
     * Different → warning, tiles stay.
     *
     * @return true if the command was valid and the step should count
     */
    @SuppressWarnings("unchecked")
    static boolean doMatch(String cmd) {
        String inner;
        try {
            inner = cmd.substring(6, cmd.length() - 1);
        } catch (StringIndexOutOfBoundsException e) {
            lastMessage = RED + "Error: Invalid Match format. Use: Match(i,j)" + RESET;
            return false;
        }

        String[] parts = inner.split(",");
        if (parts.length != 2) {
            lastMessage = RED + "Error: Match requires exactly two indices. Use: Match(i,j)" + RESET;
            return false;
        }

        int i, j;
        try {
            i = Integer.parseInt(parts[0].trim()) - 1;
            j = Integer.parseInt(parts[1].trim()) - 1;
        } catch (NumberFormatException e) {
            lastMessage = RED + "Error: Indices must be integers 1–" + SET_COUNT + ". Use: Match(i,j)" + RESET;
            return false;
        }

        if (i < 0 || i >= SET_COUNT) {
            lastMessage = RED + "Error: First index out of range (must be 1–" + SET_COUNT + ")." + RESET;
            return false;
        }
        if (j < 0 || j >= SET_COUNT) {
            lastMessage = RED + "Error: Second index out of range (must be 1–" + SET_COUNT + ")." + RESET;
            return false;
        }
        if (i == j) {
            lastMessage = RED + "Error: Cannot match a set with itself." + RESET;
            return false;
        }
        if (sets[i].isEmpty()) {
            lastMessage = RED + "Error: Set" + (i + 1) + " is empty." + RESET;
            return false;
        }
        if (sets[j].isEmpty()) {
            lastMessage = RED + "Error: Set" + (j + 1) + " is empty." + RESET;
            return false;
        }

        char tile1 = (Character) sets[i].peek();
        char tile2 = (Character) sets[j].peek();

        if (tile1 == tile2) {
            sets[i].pop();
            sets[j].pop();
            score += 5;
            lastMessage = GREEN + "MATCH! '" + tile1 + "' removed from Set" + (i + 1)
                    + " and Set" + (j + 1) + ".  +5 pts  →  Score: " + score + RESET;
        } else {
            lastMessage = YELLOW + "No match: Set" + (i + 1) + " top [" + tile1
                    + "] vs Set" + (j + 1) + " top [" + tile2 + "]. Tiles remain." + RESET;
        }

        return true;
    }

    /**
     * Handles AddSet(i): moves the front of the reserve queue onto Set-i.
     * If Set-i is full the letter is returned to the reserve queue.
     * If shift rights are exhausted, applying AddSet costs -2 points.
     *
     * @return true if the command was valid and the step should count
     */
    @SuppressWarnings("unchecked")
    static boolean doAddSet(String cmd) {
        String inner;
        try {
            inner = cmd.substring(7, cmd.length() - 1);
        } catch (StringIndexOutOfBoundsException e) {
            lastMessage = RED + "Error: Invalid AddSet format. Use: AddSet(i)" + RESET;
            return false;
        }

        int i;
        try {
            i = Integer.parseInt(inner.trim()) - 1;
        } catch (NumberFormatException e) {
            lastMessage = RED + "Error: Index must be an integer 1–" + SET_COUNT + "." + RESET;
            return false;
        }

        if (i < 0 || i >= SET_COUNT) {
            lastMessage = RED + "Error: Set index out of range (must be 1–" + SET_COUNT + ")." + RESET;
            return false;
        }
        if (reserveQueue.isEmpty()) {
            lastMessage = RED + "Error: Reserve queue is empty." + RESET;
            return false;
        }

        char letter = reserveQueue.dequeue();
        String msg;

        if (sets[i].isFull()) {
            reserveQueue.enqueue(letter);
            msg = YELLOW + "Set" + (i + 1) + " is full! '" + letter + "' returned to reserve queue." + RESET;
        } else {
            sets[i].push(letter);
            msg = CYAN + "Added '" + letter + "' to Set" + (i + 1) + "." + RESET;
        }

        if (shiftRights == 0) {
            score -= 2;
            msg += "  " + RED + "No shifts left! Penalty -2 pts  →  Score: " + score + RESET;
        }

        lastMessage = msg;
        return true;
    }

    /**
     * Handles ShiftQueue: moves the front element of the reserve queue to the rear.
     * Consumes one shift right. Fails (no step counted) if shift rights are exhausted.
     *
     * @return true if the shift was performed and the step should count
     */
    static boolean doShiftQueue() {
        if (shiftRights <= 0) {
            lastMessage = RED + "Warning: No shift rights remaining! Cannot shift." + RESET;
            return false;
        }
        if (reserveQueue.isEmpty()) {
            lastMessage = RED + "Warning: Reserve queue is empty. Nothing to shift." + RESET;
            return false;
        }

        char front = reserveQueue.dequeue();
        reserveQueue.enqueue(front);
        shiftRights--;

        lastMessage = CYAN + "Queue shifted. '" + front + "' moved to the rear."
                + "  Remaining shifts: " + shiftRights + RESET;
        return true;
    }

    /**
     * Automatic tile addition triggered every 3 valid steps.
     * Takes the front of the supplementary queue and adds it to the set
     * with the fewest tiles. If that set is full, the tile is returned.
     */
    @SuppressWarnings("unchecked")
    static void doAutoAdd() {
        if (supplementaryQueue.isEmpty()) {
            lastMessage += "\n" + YELLOW + "[Auto-Add] Supplementary queue empty. Skipped." + RESET;
            return;
        }

        int minIdx  = 0;
        int minSize = sets[0].size();
        for (int i = 1; i < SET_COUNT; i++) {
            if (sets[i].size() < minSize) {
                minSize = sets[i].size();
                minIdx  = i;
            }
        }

        char letter = supplementaryQueue.dequeue();

        if (sets[minIdx].isFull()) {
            supplementaryQueue.enqueue(letter);
            lastMessage += "\n" + YELLOW + "[Auto-Add] Set" + (minIdx + 1)
                    + " full! '" + letter + "' returned to supplementary queue." + RESET;
        } else {
            sets[minIdx].push(letter);
            lastMessage += "\n" + CYAN + "[Auto-Add] '" + letter
                    + "' added to Set" + (minIdx + 1) + " (fewest tiles)." + RESET;
        }
    }

    // ============================================================
    //  DISPLAY HELPERS
    // ============================================================

    /** Clears the terminal screen using ANSI escape codes. */
    static void clearScreen() {
        System.out.print("\u001B[2J\u001B[H");
        System.out.flush();
    }

    /** Clears and redraws the entire game screen. */
    @SuppressWarnings("unchecked")
    static void displayGameState() {
        clearScreen();

        // ── Header ──────────────────────────────────────────────
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.println(BOLD + "          TILE  MATCHING  GAME"            + RESET);
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.printf(" Player: %-14s  Step: %d / %d%n",
                BOLD + playerName + RESET, stepCount, maxSteps);
        System.out.printf(" Score:  %-14s  Shifts left: %d%n",
                BOLD + GREEN + score + RESET, shiftRights);
        System.out.println(BOLD + "------------------------------------------" + RESET);

        // ── Tile sets ───────────────────────────────────────────
        System.out.println();
        for (int i = 0; i < SET_COUNT; i++) {
            System.out.printf(" Set%d [%2d/%2d]  ", (i + 1), sets[i].size(), SET_CAPACITY);
            printStack(sets[i]);
            System.out.println();
        }

        // ── Queues ──────────────────────────────────────────────
        System.out.println();
        System.out.print(" Reserve Queue       ");
        printQueue(reserveQueue);
        System.out.println();

        System.out.print(" Supplementary Queue ");
        printQueue(supplementaryQueue);
        System.out.println();

        // ── Last message ────────────────────────────────────────
        System.out.println(BOLD + "------------------------------------------" + RESET);
        if (!lastMessage.isEmpty()) {
            System.out.println(" " + lastMessage);
        }
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.println(" Commands:  Match(i,j)   AddSet(i)   ShiftQueue   F");
        System.out.println(BOLD + "==========================================" + RESET);
    }

    /**
     * Prints a Character stack from bottom to top.
     * Uses a temporary stack to reverse and restore.
     * Format:  A  B  C  ←top
     */
    @SuppressWarnings("unchecked")
    static void printStack(Stack<Character> stack) {
        int sz = stack.size();

        // Fill unused slots with dots for a fixed-width visual
        int empty = SET_CAPACITY - sz;
        for (int k = 0; k < empty; k++) System.out.print(WHITE + "·" + RESET + " ");

        if (sz > 0) {
            Stack<Character> temp = new Stack<>(SET_CAPACITY);
            for (int k = 0; k < sz; k++) temp.push((Character) stack.pop());
            for (int k = 0; k < sz; k++) {
                char c = (Character) temp.pop();
                boolean isTop = (k == sz - 1);
                if (isTop) System.out.print(BOLD + GREEN + c + RESET);
                else       System.out.print(c);
                System.out.print(" ");
                stack.push(c);
            }
        }

        System.out.print(BOLD + "←top" + RESET);
    }

    /**
     * Prints a Character queue from front to rear.
     * Uses a temporary queue to drain and restore.
     * Format:  [front→  A  B  C  ]
     */
    static void printQueue(Queue<Character> queue) {
        int sz = queue.size();
        System.out.print("[front→ ");

        if (sz > 0) {
            Queue<Character> temp = new Queue<>(sz + 5);
            for (int k = 0; k < sz; k++) {
                char c = queue.dequeue();
                System.out.print(c + " ");
                temp.enqueue(c);
            }
            for (int k = 0; k < sz; k++) queue.enqueue(temp.dequeue());
        }

        System.out.print("]");
    }

    // ============================================================
    //  HIGH SCORE TABLE
    // ============================================================

    /**
     * Reads the high score table from HighScoreTable.txt.
     * Each line has the format: "PlayerName Score"
     * Loads at most HIGH_SCORE_MAX entries.
     */
    static void loadHighScores() {
        File file = new File(HIGH_SCORE_FILE);
        if (!file.exists()) return;

        try (BufferedReader br = new BufferedReader(new FileReader(file))) {
            String line;
            int count = 0;
            while ((line = br.readLine()) != null && count < HIGH_SCORE_MAX) {
                line = line.trim();
                if (line.isEmpty()) continue;
                int lastSpace = line.lastIndexOf(' ');
                if (lastSpace < 0) continue;
                try {
                    String name = line.substring(0, lastSpace);
                    int    sc   = Integer.parseInt(line.substring(lastSpace + 1).trim());
                    highScoreTable.enqueue(new PlayerScore(name, sc));
                    count++;
                } catch (NumberFormatException ignored) { /* skip malformed lines */ }
            }
        } catch (IOException e) {
            System.out.println("Note: Could not load '" + HIGH_SCORE_FILE + "'. Starting fresh.");
        }
    }

    /**
     * Inserts the new player/score into the high score table at the correct position.
     *
     * Ordering rules:
     *  - Table is sorted descending by score.
     *  - A new player with the SAME score appears ABOVE existing players with the same score.
     *  - Table is capped at HIGH_SCORE_MAX; the lowest entry is dropped if needed.
     */
    static void updateHighScores(String name, int newScore) {
        Queue<PlayerScore> newTable = new Queue<>(HIGH_SCORE_MAX + 1);
        boolean inserted  = false;
        int     count     = 0;
        int     tableSize = highScoreTable.size();

        for (int i = 0; i < tableSize; i++) {
            PlayerScore ps = highScoreTable.dequeue();

            if (!inserted && ps.getScore() <= newScore && count < HIGH_SCORE_MAX) {
                newTable.enqueue(new PlayerScore(name, newScore));
                inserted = true;
                count++;
            }

            if (count < HIGH_SCORE_MAX) {
                newTable.enqueue(ps);
                count++;
            }
        }

        if (!inserted && count < HIGH_SCORE_MAX) {
            newTable.enqueue(new PlayerScore(name, newScore));
        }

        highScoreTable = newTable;
    }

    /** Prints the high score table to the console. */
    static void displayHighScores() {
        System.out.println();
        System.out.println(BOLD + "==========================================" + RESET);
        System.out.println(BOLD + "           HIGH SCORE TABLE"               + RESET);
        System.out.println(BOLD + "==========================================" + RESET);

        int sz = highScoreTable.size();
        if (sz == 0) {
            System.out.println("  (No scores recorded yet)");
        } else {
            Queue<PlayerScore> temp = new Queue<>(HIGH_SCORE_MAX + 1);
            for (int i = 0; i < sz; i++) {
                PlayerScore ps = highScoreTable.dequeue();
                System.out.printf("  %2d. %-20s %s%d%s%n",
                        (i + 1), ps.getName(), BOLD + GREEN, ps.getScore(), RESET);
                temp.enqueue(ps);
            }
            for (int i = 0; i < sz; i++) highScoreTable.enqueue(temp.dequeue());
        }

        System.out.println(BOLD + "==========================================" + RESET);
    }

    /**
     * Saves the high score table to HighScoreTable.txt.
     * Format: one "PlayerName Score" entry per line.
     */
    static void saveHighScores() {
        try (PrintWriter pw = new PrintWriter(new FileWriter(HIGH_SCORE_FILE))) {
            int sz = highScoreTable.size();
            Queue<PlayerScore> temp = new Queue<>(HIGH_SCORE_MAX + 1);
            for (int i = 0; i < sz; i++) {
                PlayerScore ps = highScoreTable.dequeue();
                pw.println(ps.getName() + " " + ps.getScore());
                temp.enqueue(ps);
            }
            for (int i = 0; i < sz; i++) highScoreTable.enqueue(temp.dequeue());
        } catch (IOException e) {
            System.out.println("Error: Could not save high scores: " + e.getMessage());
        }
    }

    // ============================================================
    //  UTILITIES
    // ============================================================

    /** Returns true if every tile set is empty. */
    static boolean allSetsEmpty() {
        for (int i = 0; i < SET_COUNT; i++) {
            if (!sets[i].isEmpty()) return false;
        }
        return true;
    }

    /**
     * Returns A–Z in a randomly shuffled order (Fisher-Yates).
     * char[] is used only for initialisation, not as a game data structure.
     */
    static char[] shuffleAlphabet(Random random) {
        char[] arr = new char[26];
        for (int i = 0; i < 26; i++) arr[i] = (char) ('A' + i);
        for (int i = 25; i > 0; i--) {
            int  j   = random.nextInt(i + 1);
            char tmp = arr[i];
            arr[i]   = arr[j];
            arr[j]   = tmp;
        }
        return arr;
    }
}
