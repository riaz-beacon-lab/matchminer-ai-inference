<template>
  <header class="flex h-14 items-center gap-3 border-b px-4">
    <RouterLink to="/" class="font-semibold">MatchMiner-AI</RouterLink>
    <span class="text-sm text-muted-foreground">Clinical trial matching</span>
  </header>
  <main class="min-h-[calc(100vh-3.5rem)] bg-muted/30">
    <RouterView />
  </main>
</template>
