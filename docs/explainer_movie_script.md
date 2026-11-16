# Stop-action explainer: how my network counts fingers

**Length:** about 3 minutes (a shorter 2-minute version is at the end).
**Your voice** over paper-and-pencil stop-motion. Everything on the table is made from paper, pencil and a few cards, so it is quick to build.
**What it has to explain:** the CNN and pooling (the assignment's words). It also touches on learning and on why the board only runs the network.

---

## Before you film (15 minutes)

You need: a phone on a tripod or a stack of books looking straight down at the table, white paper, a pencil, scissors, 12 small cards (for numbers), a thin sheet of clear plastic or tracing paper, a sticky note.

- **Speed:** this is a slow, clear explanation, so each photo stays on screen for **about one second** (the whole film is about 190 photos for 3.5 minutes; see the "photos" column). A stop-motion app is easiest (Stop Motion Studio is free): it lets you set how long each photo stays and record the voice afterwards. Where a scene is longer than its photos, hold the last photo a little longer.
- **Light:** the same lamp, not the window, so the pictures don't flicker. Don't touch the phone between photos.
- **Voice:** record it **after** the pictures, in one go, reading the lines below slowly. Then drop each line under its scene.
- **Make one big drawing of a hand** (a simple shape with five fingers) and a **grid of 8 × 8 squares** (each square 2 cm) on paper with numbers 0 to 9 written in them: that is "the picture" for the first scenes. The real picture is 64 × 64, but 8 × 8 is enough to show the idea.

---

## The scenes

| # | Seconds | On the table (and what moves between photos) | Voice-over | Photos |
|---|---|---|---|---|
| 1 | 0:00 to 0:12 | The paper box with a small door. Your hand drawing slides in front of a tiny cardboard camera. The door pops open. | "I built a box that opens when you show it the right fingers. A neural network looks at my hand and counts how many fingers I'm holding. Here is how it does that." | 20 |
| 2 | 0:12 to 0:30 | The hand drawing. A square frame is placed over it, then the 8 × 8 numbered grid replaces it (cross-fade by swapping the paper). | "To the computer, a picture is just a grid of numbers: how bright each little square is. My camera cuts out the square around my hand and shrinks it to 64 by 64 pixels, and each pixel has three numbers, for red, green and blue." | 14 |
| 3 | 0:30 to 1:05 | The numbered grid. A **3 × 3 window** cut from the clear plastic, with filter numbers written on it, sits in the top-left corner. Move it one square at a time to the right (6 to 8 photos). Each time, write the result in a second, empty grid, square by square. | "The first trick is the convolution. I take a tiny window, a filter, put it on the picture, multiply each number under it by the filter's number, and add them all up. That gives one new number. Then I slide the window one square and do it again. The filter is a little pattern detector: it gives a big number where the picture looks like its pattern, like an edge. My network has sixteen filters in its first layer, so it makes sixteen new pictures." | 30 |
| 4 | 1:05 to 1:15 | The new grid. Flip over the cards with negative numbers so they show 0. | "Then comes ReLU. Every negative number becomes zero. It keeps only the places where the filter said 'yes, I see it'." | 10 |
| 5 | 1:15 to 1:45 | A 4 × 4 grid of numbers. Put a sticky note over each 2 × 2 block, circle the biggest number, then build a new **2 × 2** grid with only the circled numbers. | "Next is pooling. I look at each block of two by two numbers and keep only the biggest one. The picture becomes half as wide and half as tall, so there is less to compute, and the strongest signals stay. It also means that if a finger moves by a pixel or two, the answer hardly changes." | 24 |
| 6 | 1:45 to 2:05 | Three stacks of paper squares get smaller and thicker from left to right (64, 32, 16, 8 written on them). Write the filter sizes above: 5 × 5, 3 × 3, 3 × 3. | "I do this three times, with filters of different sizes, and pool every time, so the picture shrinks from 64 to 32, to 16, to 8. The first layer sees edges. The later layers see combinations of edges, like a fingertip, or the gap between two fingers." | 16 |
| 7 | 2:05 to 2:20 | Each stack is squeezed into a small strip. The three strips slide next to each other and are taped into **one long strip**. Write "1,792" on it. | "Then I squeeze each layer down to a small grid, and join the three side by side into one long list: 1,792 numbers. That is a summary of the whole hand, at three different scales." | 14 |
| 8 | 2:20 to 2:35 | Six paper bars labelled 0 to 5. They grow to different heights (3 photos), and the one for 3 is the tallest. Put a crown on it (a sticky note). | "A last layer turns those 1,792 numbers into six scores, one for every number of fingers from zero to five, and softmax turns them into probabilities. The biggest one wins. Here the network is ninety percent sure I'm showing three fingers." | 14 |
| 9 | 2:35 to 3:00 | The six bars again, but with the wrong one tallest. A big red "WRONG" card. A small hand moves tiny numbered paper pieces ("35,110 knobs") a little. The bars improve over several photos. | "At the start the filters are random and the answers are wrong. For every training picture I measure how wrong the answer is, with cross-entropy, and then nudge all 35,110 numbers a tiny bit to be less wrong. It's gradient descent, the same idea as fitting Anna's V, just with many more numbers. I trained it on 2,400 pictures of my hand on my laptop." | 24 |
| 10 | 3:00 to 3:20 | Two paper drawings: a laptop with a "train" label, and a little board with a "run" label. A paper arrow carries a small box ("the finished numbers") from the laptop to the board. | "Training happens on the laptop. The UNO Q only runs the finished network: about twenty-eight milliseconds for each picture, three times slower than my laptop, but fast enough for a lock." | 12 |
| 11 | 3:20 to 3:30 | The box from scene 1. A hand shows three fingers, then two, and the door opens only for the right ones. | "And that's it: the right fingers open the door, the wrong ones don't. Thanks for watching." | 12 |

**Total:** about 190 photos for the whole thing (about one photo a second). Allow about an hour and a half to shoot, and 20 minutes to add the voice.

---

## If you are short of time: the 2-minute version

Keep scenes **1, 3, 5, 7, 8 and 9**, and trim each voice-over to its first two sentences. That still has the convolution, the pooling, the joining of the three layers, the decision and the learning, and is about 110 photos.

## Checks before you export

- Does the film say the word **pooling** and show the 2 × 2 → biggest-number idea? (scene 5)
- Does it say **CNN**, or "convolutional neural network", once out loud? (add it to scene 1: "...a convolutional neural network, a CNN...")
- Is it your own voice, and can every sentence be heard over the paper noise? Record in a quiet room, close to the phone.
- Length: under about 3.5 minutes. Put it in the Notion page as video number 9.
