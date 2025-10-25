function isPalindrome(s) {
  const cleanedString = s.toLowerCase().replace(/[^a-z0-9]/g, '');
  return cleanedString === cleanedString.split('').reverse().join('');
}

function assert(cond, message) { if (!cond) throw new Error(message); }
assert(isPalindrome("racecar"), "Failed palindrome test on word 'racecar'");
assert(isPalindrome("RaceCar"), "Failed palindrome test on word 'RaceCar'");
assert(isPalindrome("A man, a plan, a canal: Panama!"), "Failed palindrome test on sentence 'A man, a plan, a canal: Panama!'");
assert(!isPalindrome("hello"), "Incorrectly passed palindrome test on word 'hello'");
assert(isPalindrome("No 'x' in Nixon"), "Failed palindrome test on phrase 'No 'x' in Nixon'");
console.log("ALL_PASS");
module.exports = { isPalindrome };
